'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

const input =
  'w-full rounded-lg border border-hairline bg-canvas px-3 py-2.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none transition-colors'

export default function SignupPage() {
  const router = useRouter()
  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', password: '',
  })
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
        body: JSON.stringify(form),
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
            type="password" required minLength={8}
            autoComplete="new-password"
            placeholder="password (8+ characters)" value={form.password}
            onChange={set('password')} className={input}
          />
          {err && <p className="text-xs text-defensive">{err}</p>}
          <button
            type="submit" disabled={busy}
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
