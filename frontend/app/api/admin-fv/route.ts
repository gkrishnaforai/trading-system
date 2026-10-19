import { NextRequest, NextResponse } from 'next/server'
import { getToken, getUser } from '@/lib/auth'
import { BASE } from '@/lib/api'

/** POST /api/admin-fv -> <worker>/api/v1/fundamentals/fair-value-v2/run
    Admin-only: a fair-value recompute is a write — it persists a run
    that every page reads. The board proxy can't reach this path (it
    maps /api/v1/board/*); this route keeps the same role gate. */
export async function POST(req: NextRequest) {
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
  try {
    const res = await fetch(`${BASE}/api/v1/fundamentals/fair-value-v2/run`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: await req.text(),
      cache: 'no-store',
      signal: AbortSignal.timeout(180_000),
    })
    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('Content-Type') ?? 'application/json' },
    })
  } catch {
    return NextResponse.json(
      { error: 'worker unreachable or timed out' }, { status: 502 },
    )
  }
}
