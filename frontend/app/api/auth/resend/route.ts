import { NextResponse } from 'next/server'
import { authedFetch } from '@/lib/auth'

export const dynamic = 'force-dynamic'

/** POST → resend the verification email for the signed-in user. */
export async function POST() {
  const res = await authedFetch('/users/resend-verification', {
    method: 'POST',
  })
  if (!res) {
    return NextResponse.json(
      { error: 'auth service unreachable' }, { status: 502 })
  }
  const j = (await res.json().catch(() => ({}))) as {
    sent?: boolean; already?: boolean; detail?: string
  }
  if (!res.ok) {
    return NextResponse.json(
      { error: j.detail ?? 'resend failed' }, { status: 400 })
  }
  return NextResponse.json(j)
}
