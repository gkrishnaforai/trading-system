import { NextRequest, NextResponse } from 'next/server'
import { signIn, setSessionCookie } from '@/lib/auth'

export const dynamic = 'force-dynamic'

/** POST { email, password } → session cookie + user, or an error the
    form can show. Provider-agnostic: lib/auth picks local|supabase. */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  const email = String(body.email ?? '').trim()
  const password = String(body.password ?? '')
  if (!email || !password) {
    return NextResponse.json(
      { error: 'email and password required' }, { status: 400 })
  }
  const res = await signIn(email, password)
  if (!res) {
    return NextResponse.json(
      { error: 'auth service unreachable' }, { status: 502 })
  }
  if ('error' in res) {
    return NextResponse.json({ error: res.error }, { status: 401 })
  }
  setSessionCookie(res.token)
  return NextResponse.json({ user: res.user })
}
