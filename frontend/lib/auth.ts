/** Session auth — AUTH_PROVIDER picks the backend ("local" = our
    Postgres users table + worker-issued JWT in the mp_token cookie;
    "supabase" is the future provider — swap the provider functions,
    not the call sites).

    local flow: /api/auth/login|signup call the worker, which mints a
    ~7d JWT; we keep it in an httpOnly cookie. getToken() serves that
    session to worker-bound calls so portfolio data is per-user. */
import { cookies } from 'next/headers'
import { BASE } from './api'

export const AUTH_PROVIDER = process.env.AUTH_PROVIDER ?? 'local'

const USERNAME = process.env.MP_LOCAL_USERNAME ?? 'trader'
const PASSWORD = process.env.MP_LOCAL_PASSWORD ?? 'marketpulse-local'
const EMAIL = process.env.MP_LOCAL_EMAIL ?? 'trader@local.dev'

export type SessionUser = {
  role: string
  username?: string
  email?: string
}

async function postJson(path: string, body: unknown) {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
    signal: AbortSignal.timeout(20_000),
  })
}

/** Device-account login — the pre-auth shim kept as a fallback for
    server-to-worker calls with no user session (internal callers,
    pre-login contexts). Set MP_DEVICE_ACCOUNT_AUTH=off to disable. */
async function deviceLogin(): Promise<string | null> {
  if (process.env.MP_DEVICE_ACCOUNT_AUTH === 'off') return null
  try {
    let res = await postJson('/api/v2/portfolio/users/login',
      { username: USERNAME, password: PASSWORD })
    if (res.status === 400 || res.status === 401) {
      await postJson('/api/v2/portfolio/users/register', {
        username: USERNAME, email: EMAIL,
        password: PASSWORD, full_name: 'Osprey Desk',
      })
      res = await postJson('/api/v2/portfolio/users/login',
        { username: USERNAME, password: PASSWORD })
    }
    if (!res.ok) return null
    const j = (await res.json()) as { access_token?: string }
    return j.access_token ?? null
  } catch {
    return null
  }
}

/** Provider seam — sign a human in. Returns { token, user },
    { error } on a clean reject, null when the provider is down.
    supabase: will call supabase.auth.signInWithPassword and store its
    access token; call sites (cookie, getUser, authedFetch) don't
    change. */
export async function signIn(
  email: string, password: string,
): Promise<
  { token: string; user: SessionUser } | { error: string } | null
> {
  if (AUTH_PROVIDER === 'supabase') {
    // TODO: supabase.auth.signInWithPassword({ email, password })
    return null
  }
  try {
    const res = await postJson('/api/v2/portfolio/users/login',
      { username: email, password })
    const j = (await res.json().catch(() => ({}))) as {
      access_token?: string
      detail?: string
      user?: { role?: string; username?: string; email?: string }
    }
    if (!res.ok || !j.access_token) {
      return { error: j.detail ?? 'sign-in failed' }
    }
    return {
      token: j.access_token,
      user: {
        role: j.user?.role ?? 'basic',
        username: j.user?.username,
        email: j.user?.email,
      },
    }
  } catch {
    return null
  }
}

/** Provider seam — create a basic account. Returns { token, user }
    (auto-signed-in) or null; { error } on a clean reject. */
export async function signUp(
  firstName: string, lastName: string, email: string, password: string,
): Promise<
  { token: string; user: SessionUser } | { error: string } | null
> {
  if (AUTH_PROVIDER === 'supabase') {
    // TODO: supabase.auth.signUp({ email, password, options: { data } })
    return null
  }
  try {
    const res = await postJson('/api/v2/portfolio/users/signup', {
      first_name: firstName, last_name: lastName,
      email, password,
    })
    const j = (await res.json().catch(() => ({}))) as {
      access_token?: string
      detail?: string | Array<{ msg?: string }>
      user?: { role?: string; username?: string; email?: string }
    }
    if (!res.ok || !j.access_token) {
      const d = j.detail
      return {
        error: typeof d === 'string' ? d
          : Array.isArray(d) ? (d[0]?.msg ?? 'signup failed')
          : 'signup failed',
      }
    }
    return {
      token: j.access_token,
      user: {
        role: j.user?.role ?? 'basic',
        username: j.user?.username,
        email: j.user?.email,
      },
    }
  } catch {
    return null
  }
}

export function setSessionCookie(token: string) {
  cookies().set('mp_token', token, {
    httpOnly: true, sameSite: 'lax', path: '/',
    maxAge: 60 * 60 * 24 * 7,
  })
}

export function clearSessionCookie() {
  try { cookies().delete('mp_token') } catch { /* render ctx */ }
}

/** Token for worker-bound calls — the signed-in user's session first,
    the device account as a server-side fallback for contexts with no
    user (disable via MP_DEVICE_ACCOUNT_AUTH=off). */
export async function getToken(): Promise<string | null> {
  const t = cookies().get('mp_token')?.value
  if (t && !expired(t)) return t
  return deviceLogin()
}

function expired(token: string, skewS = 60): boolean {
  const exp = decodeClaims(token)?.exp
  if (typeof exp !== 'number') return true
  return exp * 1000 <= Date.now() + skewS * 1000
}

function decodeClaims(token: string | null): Record<string, unknown> | null {
  if (!token) return null
  try {
    const seg = token.split('.')[1]
    return JSON.parse(Buffer.from(seg, 'base64url').toString())
  } catch {
    return null
  }
}

/** Who the current request is — the session cookie's claims, or
    'anonymous' when there's no session. No device-account fallback
    here: identity must never be silently assumed. */
export async function getUser(): Promise<SessionUser> {
  const token = cookies().get('mp_token')?.value ?? null
  const claims = decodeClaims(token)
  if (!claims || expired(token ?? '')) return { role: 'anonymous' }
  return {
    role: String(claims.role ?? 'basic'),
    username: claims.username ? String(claims.username) : undefined,
    email: claims.email ? String(claims.email) : undefined,
  }
}

/** Authed fetch against the worker portfolio v2 API. */
export async function authedFetch(
  path: string, init: RequestInit = {},
): Promise<Response | null> {
  const token = await getToken()
  if (!token) return null
  try {
    return await fetch(`${BASE}/api/v2/portfolio${path}`, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
      signal: init.signal ?? AbortSignal.timeout(60_000),
    })
  } catch {
    return null
  }
}
