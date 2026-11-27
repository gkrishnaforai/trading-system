import { NextRequest, NextResponse } from 'next/server'

/** Route gate — reads the mp_token session cookie (JWT minted by the
    worker; signature is verified worker-side on every authed call, so
    claims decode is enough for routing decisions).

    - no/expired session            → /login (auth pages stay open)
    - role 'basic'                  → /portfolio + its APIs only
    - everything else               → pass through

    Flip AUTH_PROVIDER to 'supabase' later — this gate only needs a
    valid session cookie + role claim, whichever backend minted it. */

const PUBLIC_PATHS = ['/login', '/signup']
const PUBLIC_API = ['/api/auth/']

/** Paths a 'basic' session may reach — the portfolio page and the
    APIs it needs. Everything else redirects to /portfolio. */
const BASIC_ALLOWED = [
  '/portfolio',
  '/api/portfolio/',
  '/api/me',
  '/api/auth/',
]

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

  // signed-in visitors don't need the auth pages
  if (isPublicPage) {
    const url = req.nextUrl.clone()
    url.pathname = '/portfolio'
    url.search = ''
    return NextResponse.redirect(url)
  }

  const role = String(claims.role ?? 'basic')
  if (role === 'basic' &&
      !BASIC_ALLOWED.some((p) => path === p || path.startsWith(p))) {
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
