import { NextRequest, NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** POST { token } → worker consumes the emailed verification token.
    Returns { verified } or { error }. */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  const token = String(body.token ?? '')
  if (!token) {
    return NextResponse.json({ error: 'missing token' }, { status: 400 })
  }
  try {
    const res = await fetch(`${BASE}/api/v2/portfolio/users/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      cache: 'no-store',
      signal: AbortSignal.timeout(15_000),
    })
    const j = (await res.json().catch(() => ({}))) as {
      verified?: boolean; detail?: string
    }
    if (!res.ok) {
      return NextResponse.json(
        { error: j.detail ?? 'verification failed' }, { status: 400 })
    }
    return NextResponse.json({ verified: j.verified ?? true })
  } catch {
    return NextResponse.json(
      { error: 'auth service unreachable' }, { status: 502 })
  }
}
