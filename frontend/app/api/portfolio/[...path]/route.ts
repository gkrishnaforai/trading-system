import { NextRequest, NextResponse } from 'next/server'
import { getToken } from '@/lib/auth'
import { BASE } from '@/lib/api'

/** /api/portfolio/<path> -> <worker>/api/v2/portfolio/<path>
    Bearer token comes from the mp_token cookie (device account today,
    real session when auth lands). */
async function proxy(
  req: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const token = await getToken()
  if (!token) {
    return NextResponse.json(
      { error: 'portfolio auth unavailable' }, { status: 502 },
    )
  }
  const target =
    `${BASE}/api/v2/portfolio/${params.path.join('/')}${req.nextUrl.search}`
  const body = ['GET', 'HEAD'].includes(req.method)
    ? undefined : await req.text()
  try {
    const res = await fetch(target, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(60_000),
    })
    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'Content-Type':
          res.headers.get('Content-Type') ?? 'application/json',
      },
    })
  } catch {
    return NextResponse.json(
      { error: 'worker unreachable' }, { status: 502 },
    )
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE }
