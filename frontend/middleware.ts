import { NextRequest, NextResponse } from 'next/server'

/** Route gate — reads the mp_token session cookie (JWT minted by the
    worker; signature is verified worker-side on every authed call, so
    claims decode is enough for routing decisions).

    - no/expired session            → /login (auth pages stay open)
    - role 'basic'                  → /portfolio + its APIs only
    - everything else               → pass through

    Flip AUTH_PROVIDER to 'supabase' later — this gate only needs a
    valid session cookie + role claim, whichever backend minted it. */

const PUBLIC_PATHS = ['/login', '/signup', '/terms', '/verify']
const PUBLIC_API = ['/api/auth/', '/api/health']

/** Role → allowed surfaces. Group-2 advisory content (rankings,
    verdicts, scores, targets, forecasts, engine calls) is
    admin-only — everything else is the desk; the allowed sets below
    are the user-directed / factual-data surfaces plus the legal docs
    every user must be able to read. Fail-closed: an unrecognized
    role gets the basic surface. */
const BASIC_ALLOWED = [
  '/portfolio',
  '/stock',
  '/api/portfolio/',
  '/api/me',
  '/api/auth/',
  '/api/health',
  '/terms',
]

/** advanced/super-user = basic + factual read surfaces. The calendar
    page additionally strips its verdict/guide/judge chips for
    non-admin (the events themselves are public information). */
const ROLE_ALLOWED: Record<string, string[]> = {
  basic: BASIC_ALLOWED,
  advanced: [...BASIC_ALLOWED, '/calendar'],
  'super-user': [...BASIC_ALLOWED, '/calendar'],
  // admin: unrestricted — every Group-2 surface
}

function decode(token: string): Record<string, unknown> | null {
  try {
    const seg = token.split('.')[1]
    const json = atob(seg.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return null
  }
}

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname
  const token = req.cookies.get('mp_token')?.value ?? ''
  const claims = token ? decode(token) : null
  const valid = !!claims &&
    typeof claims.exp === 'number' &&
    claims.exp * 1000 > Date.now()

  const isPublicPage = PUBLIC_PATHS.some((p) => path.startsWith(p))
  const isPublicApi = PUBLIC_API.some((p) => path.startsWith(p))

  if (!valid) {
    if (isPublicPage || isPublicApi) return NextResponse.next()
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.search = path === '/' ? '' : `?next=${encodeURIComponent(path)}`
    return NextResponse.redirect(url)
  }

  // signed-in visitors don't need the auth pages — /verify excepted:
  // the emailed link must run while logged in too
  if (isPublicPage && !path.startsWith('/verify')) {
    const url = req.nextUrl.clone()
    url.pathname = '/portfolio'
    url.search = ''
    return NextResponse.redirect(url)
  }

  const role = String(claims.role ?? 'basic')
  const allowed = ROLE_ALLOWED[role] ?? (
    role === 'admin' ? null : BASIC_ALLOWED)
  if (allowed &&
      !allowed.some((p) => path === p || path.startsWith(p))) {
    const url = req.nextUrl.clone()
    url.pathname = '/portfolio'
    url.search = ''
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  // everything except Next internals and static assets
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|ico|webp|woff2?|ttf)).*)'],
}
