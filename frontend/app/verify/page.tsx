'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'

function VerifyCore() {
  const params = useSearchParams()
  const [state, setState] = useState<'working' | 'ok' | 'err'>('working')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setState('err')
      setMsg('this link is missing its token')
      return
    }
    fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then(async (r) => {
        const j = await r.json().catch(() => ({}))
        if (r.ok && j.verified) {
          setState('ok')
        } else {
          setState('err')
          setMsg(j.error ?? 'verification failed')
        }
      })
      .catch(() => {
        setState('err')
        setMsg('could not reach the auth service')
      })
  }, [params])

  return (
    <main className="mx-auto flex max-w-md flex-col items-center px-5 pt-24 text-center">
      {state === 'working' && (
        <p className="text-sm text-muted">Verifying your email…</p>
      )}
      {state === 'ok' && (
        <>
          <h1 className="text-xl font-semibold text-ink">
            Email verified
          </h1>
          <p className="pt-3 text-sm text-muted">
            Your address is confirmed — your account is fully set up.
          </p>
          <Link
            href="/portfolio"
            className="mt-6 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-white hover:brightness-110"
          >
            Go to your portfolio →
          </Link>
        </>
      )}
      {state === 'err' && (
        <>
          <h1 className="text-xl font-semibold text-ink">
            Link didn&apos;t work
          </h1>
          <p className="pt-3 text-sm text-muted">
            {msg}. Links expire after 24 hours — sign in and request a
            new one from the banner at the top of the page.
          </p>
          <Link
            href="/login"
            className="mt-6 rounded-full border border-hairline px-5 py-2 text-sm font-medium text-ink hover:border-accent"
          >
            Sign in
          </Link>
        </>
      )}
    </main>
  )
}

export default function VerifyPage() {
  return (
    <Suspense fallback={null}>
      <VerifyCore />
    </Suspense>
  )
}
