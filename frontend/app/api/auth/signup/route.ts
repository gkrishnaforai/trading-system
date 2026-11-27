import { NextRequest, NextResponse } from 'next/server'
import { signUp, setSessionCookie } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** POST { first_name, last_name, email, password } → account + session
    cookie. Email validated here (cheap) and again at the worker
    (EmailStr); every new account lands role 'basic' server-side. */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  const first = String(body.first_name ?? '').trim()
  const last = String(body.last_name ?? '').trim()
  const email = String(body.email ?? '').trim().toLowerCase()
  const password = String(body.password ?? '')
  if (!first || !last) {
    return NextResponse.json(
      { error: 'first and last name required' }, { status: 400 })
  }
  if (!EMAIL_RE.test(email)) {
    return NextResponse.json(
      { error: 'a valid email is required' }, { status: 400 })
  }
  if (password.length < 8) {
    return NextResponse.json(
      { error: 'password must be at least 8 characters' },
      { status: 400 })
  }
  const res = await signUp(first, last, email, password)
  if (!res) {
    return NextResponse.json(
      { error: 'auth service unreachable' }, { status: 502 })
  }
  if ('error' in res) {
    return NextResponse.json({ error: res.error }, { status: 400 })
  }
  setSessionCookie(res.token)
  return NextResponse.json({ user: res.user })
}
