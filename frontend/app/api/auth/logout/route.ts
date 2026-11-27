import { NextResponse } from 'next/server'
import { authedFetch, clearSessionCookie, getUser } from '@/lib/auth'

export const dynamic = 'force-dynamic'

/** POST → journal the sign-out server-side (best-effort, only when a
    real user session existed), then drop the cookie. */
export async function POST() {
  const u = await getUser()
  if (u.role !== 'anonymous') {
    await authedFetch('/users/logout', { method: 'POST' }).catch(() => null)
  }
  clearSessionCookie()
  return NextResponse.json({ ok: true })
}
