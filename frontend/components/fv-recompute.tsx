'use client'

import { useEffect, useState } from 'react'

/** Admin-only FV recompute — forces a fresh engine run (ignores the
    stored-run watermark), persists it, then reloads so every panel
    reads the new row. Renders nothing for non-admins. */
export default function FvRecompute({ sym }: { sym: string }) {
  const [admin, setAdmin] = useState(false)
  const [state, setState] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/me', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.role === 'admin') setAdmin(true) })
      .catch(() => {})
  }, [])

  if (!admin) return null

  async function run() {
    setState('running')
    setMsg(null)
    try {
      const res = await fetch('/api/admin-fv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, force_refresh: true }),
      })
      const j = await res.json().catch(() => ({}))
      const fv = j?.result?.expected_fair_value ?? j?.result?.fair_value
      if (res.ok && j?.success && fv != null) {
        setMsg(`new run → FV $${Number(fv).toFixed(2)} — reloading…`)
        setState('done')
        setTimeout(() => window.location.reload(), 1200)
      } else {
        setMsg(String(j?.error ?? j?.detail ?? 'run failed'))
        setState('error')
      }
    } catch {
      setMsg('worker unreachable')
      setState('error')
    }
  }

  return (
    <span className="inline-flex items-baseline gap-2">
      <button
        onClick={run}
        disabled={state === 'running'}
        className="font-mono text-[11px] text-accent hover:text-ink disabled:opacity-50"
      >
        {state === 'running' ? '… recomputing' : '↻ recompute'}
      </button>
      {msg && (
        <span className={`text-[11px] ${state === 'error' ? 'text-defensive' : 'text-muted'}`}>
          {msg}
        </span>
      )}
    </span>
  )
}
