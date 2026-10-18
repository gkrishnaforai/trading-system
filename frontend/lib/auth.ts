/** Interim auth — provisions a device-local account on the worker's
    portfolio API and caches its JWT in an httpOnly cookie. When real
    sign-in lands, this becomes the session lookup; call sites keep
    working because they only ask for a token. */
import { cookies } from 'next/headers'
import { BASE } from './api'

const USERNAME = process.env.MP_LOCAL_USERNAME ?? 'trader'
const PASSWORD = process.env.MP_LOCAL_PASSWORD ?? 'marketpulse-local'
const EMAIL = process.env.MP_LOCAL_EMAIL ?? 'trader@local.dev'

async function postJson(path: string, body: unknown) {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  })
}

async function login(): Promise<string | null> {
  try {
    let res = await postJson('/api/v2/portfolio/users/login',
      { username: USERNAME, password: PASSWORD })
    if (res.status === 400 || res.status === 401) {
      // first run — provision the local account, then log in
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

function setCookie(token: string) {
  try {
    // works inside route handlers; silently skipped in RSC render
    cookies().set('mp_token', token, {
      httpOnly: true, sameSite: 'lax', path: '/',
      maxAge: 60 * 60 * 24 * 30,
    })
  } catch { /* render context — token still returned for this request */ }
}

export async function getToken(): Promise<string | null> {
  const t = cookies().get('mp_token')?.value
  if (t) return t
  const fresh = await login()
  if (fresh) setCookie(fresh)
  return fresh
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

/** Role + identity for the current session. Tokens minted before the
    role claim existed fall through to a fresh login. UI gate only —
    the worker independently verifies the claim server-side. */
export async function getUser(): Promise<{ role: string; username?: string }> {
  const first = decodeClaims(await getToken())
  if (first?.role) {
    return { role: String(first.role), username: first.username ? String(first.username) : undefined }
  }
  const fresh = await login()
  if (fresh) setCookie(fresh)
  const claims = decodeClaims(fresh)
  return {
    role: String(claims?.role ?? 'user'),
    username: claims?.username ? String(claims.username) : undefined,
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
    })
  } catch {
    return null
  }
}
