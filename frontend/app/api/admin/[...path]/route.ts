import { NextRequest, NextResponse } from 'next/server'
import { getToken, getUser } from '@/lib/auth'
import { BASE } from '@/lib/api'

/** /api/admin/<path> -> <worker>/api/v1/board/<path>
    Admin-role gate: job catalog mutations and manual runs are the
    site's most powerful surface, so the proxy refuses non-admins.
    The worker endpoints themselves stay open for the Streamlit ops
    dashboard (internal network), same as today. */
async function proxy(
  req: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const { role } = await getUser()
  if (role !== 'admin') {
    return NextResponse.json(
      { error: 'admin access required' }, { status: 403 },
    )
  }
  const token = await getToken()
  if (!token) {
    return NextResponse.json(
      { error: 'auth unavailable' }, { status: 502 },
    )
  }
  const target =
    `${BASE}/api/v1/board/${params.path.join('/')}${req.nextUrl.search}`
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
