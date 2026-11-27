'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

const input =
  'w-full rounded-lg border border-hairline bg-canvas px-3 py-2.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none transition-colors'

const COMMON_PASSWORDS = new Set([
  'password', 'password1', 'password123', '12345678', '123456789',
  '1234567890', 'qwerty123', 'letmein123', 'iloveyou', 'admin123',
  'welcome1', 'changeme', 'trustno1', 'dragon123', 'football1',
])

const RULES: Array<{ label: string; ok: (p: string) => boolean }> = [
  { label: '10+ characters', ok: (p) => p.length >= 10 },
  { label: 'a lowercase letter', ok: (p) => /[a-z]/.test(p) },
  { label: 'an uppercase letter', ok: (p) => /[A-Z]/.test(p) },
  { label: 'a number', ok: (p) => /[0-9]/.test(p) },
  {
    label: 'not a common password',
    ok: (p) => !COMMON_PASSWORDS.has(p.toLowerCase().trim()),
  },
]

export default function SignupPage() {
  const router = useRouter()
  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', password: '',
  })
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  function set(k: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, agreed_terms: agreed }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setErr(j?.error ?? 'signup failed')
        return
      }
      router.push('/portfolio')
      router.refresh()
    } catch {
      setErr('could not reach the auth service')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main>
      <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-5 pb-20">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Osprey Desk
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Create <span className="text-accent">account</span>
        </h1>
        <p className="pt-2 text-[13px] text-muted">
          New accounts start with portfolio access.
        </p>

        <form onSubmit={submit} className="mt-8 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input
              required autoComplete="given-name"
              placeholder="first name" value={form.first_name}
              onChange={set('first_name')} className={input}
            />
            <input
              required autoComplete="family-name"
              placeholder="last name" value={form.last_name}
              onChange={set('last_name')} className={input}
            />
          </div>
          <input
            type="email" required autoComplete="email"
            placeholder="email" value={form.email}
            onChange={set('email')} className={input}
          />
          <input
            type="password" required minLength={10}
            autoComplete="new-password"
            placeholder="password" value={form.password}
            onChange={set('password')} className={input}
          />
          {form.password.length > 0 && (
            <ul className="space-y-0.5 px-1 text-[11px]">
              {RULES.map((r) => {
                const pass = r.ok(form.password)
                return (
                  <li key={r.label}
                    className={pass ? 'text-aggressive' : 'text-faint'}>
                    {pass ? '✓' : '·'} {r.label}
                  </li>
                )
              })}
            </ul>
          )}
          <label className="flex items-start gap-2 px-1 pt-1 text-[12px] text-muted">
            <input
              type="checkbox" required checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 accent-[#EA580C]"
            />
            <span>
              I agree to the{' '}
              <Link href="/terms" className="text-accent hover:underline">
                Terms of Use &amp; disclosures
              </Link>
              , including that this platform provides research and
              education — not investment advice.
            </span>
          </label>
          {err && <p className="text-xs text-defensive">{err}</p>}
          <button
            type="submit"
            disabled={busy || !agreed ||
              !RULES.every((r) => r.ok(form.password))}
            className="w-full rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-canvas transition-colors hover:bg-accent disabled:opacity-40"
          >
            {busy ? 'creating…' : 'create account'}
          </button>
        </form>

        <p className="pt-6 text-center text-xs text-faint">
          Already have an account?{' '}
          <Link href="/login" className="text-accent hover:underline">
            sign in
          </Link>
        </p>
      </div>
    </main>
  )
}
