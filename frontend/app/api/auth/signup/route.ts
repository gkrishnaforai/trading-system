import { NextRequest, NextResponse } from 'next/server'
import { signUp, setSessionCookie } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const COMMON_PASSWORDS = new Set([
  'password', 'password1', 'password123', '12345678', '123456789',
  '1234567890', 'qwerty123', 'letmein123', 'iloveyou', 'admin123',
  'welcome1', 'changeme', 'trustno1', 'dragon123', 'football1',
])

/** Mirrors the worker's password_errors — reject weak passwords at the
    door so a bad request never reaches the worker; the worker checks
    again for direct API callers. */
function passwordErrors(p: string): string[] {
  const errs: string[] = []
  if (p.length < 10) errs.push('at least 10 characters')
  if (!/[a-z]/.test(p)) errs.push('a lowercase letter')
  if (!/[A-Z]/.test(p)) errs.push('an uppercase letter')
  if (!/[0-9]/.test(p)) errs.push('a number')
  if (COMMON_PASSWORDS.has(p.toLowerCase().trim()))
    errs.push('not a commonly-used password')
  return errs
}

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
  const weak = passwordErrors(password)
  if (weak.length) {
    return NextResponse.json(
      { error: `password needs ${weak.join(', ')}` }, { status: 400 })
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
