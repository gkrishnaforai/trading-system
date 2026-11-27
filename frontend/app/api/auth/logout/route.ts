import { NextResponse } from 'next/server'
import { clearSessionCookie } from '@/lib/auth'

export const dynamic = 'force-dynamic'

/** POST → drop the session cookie; the client then routes to /login. */
export async function POST() {
  clearSessionCookie()
  return NextResponse.json({ ok: true })
}
