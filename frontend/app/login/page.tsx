'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useState, Suspense } from 'react'

const input =
  'w-full rounded-lg border border-hairline bg-canvas px-3 py-2.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none transition-colors'

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setErr(j?.error ?? 'sign-in failed')
        return
      }
      const next = params.get('next')
      router.push(next && next.startsWith('/') ? next : '/portfolio')
      router.refresh()
    } catch {
      setErr('could not reach the auth service')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-5 pb-20">
      <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
        Osprey Desk
      </div>
      <h1 className="pt-3 font-semibold text-display text-ink">
        Sign <span className="text-accent">in</span>
      </h1>
      <p className="pt-2 text-[13px] text-muted">
        Your desk, your book — one account.
      </p>

      <form onSubmit={submit} className="mt-8 space-y-3">
        <input
          type="email" required autoComplete="email"
          placeholder="email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={input}
        />
        <input
          type="password" required autoComplete="current-password"
          placeholder="password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={input}
        />
        {err && <p className="text-xs text-defensive">{err}</p>}
        <button
          type="submit" disabled={busy}
          className="w-full rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-canvas transition-colors hover:bg-accent disabled:opacity-40"
        >
          {busy ? 'signing in…' : 'sign in'}
        </button>
      </form>

      <p className="pt-6 text-center text-xs text-faint">
        No account?{' '}
        <Link href="/signup" className="text-accent hover:underline">
          create one
        </Link>
      </p>
    </div>
  )
}

export default function LoginPage() {
  return (
    <main>
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  )
}
