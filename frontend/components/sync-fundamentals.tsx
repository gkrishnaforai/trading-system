'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

/** Admin sync — POSTs the worker's fv-refresh (the full post-print
    chain: FMP bundle refetch → flywheel → fundamental rescore → FV
    re-resolve + fv_delta) through the admin proxy, then repaints so
    the fundamentals card, FV section and print line all show the new
    inputs at once. Rendered only for role=admin — the proxy enforces
    it server-side too. */
export function SyncFundamentals({ sym }: { sym: string }) {
  const router = useRouter()
  const [state, setState] = useState<'idle' | 'run' | 'ok' | 'err'>('idle')
  const [note, setNote] = useState<string | null>(null)

  async function sync() {
    setState('run')
    setNote(null)
    try {
      const res = await fetch(
        `/api/admin/symbol/${encodeURIComponent(sym)}/fv-refresh`,
        { method: 'POST' },
      )
      const j = await res.json().catch(() => null)
      if (!res.ok) throw new Error(j?.error || `HTTP ${res.status}`)
      const fvd = j?.fv_delta
      setNote(
        fvd?.before != null && fvd?.after != null
          ? `FV $${Number(fvd.before).toFixed(0)} → $${Number(fvd.after).toFixed(0)}`
            + (fvd.delta_pct != null
              ? ` (${fvd.delta_pct > 0 ? '+' : ''}${(fvd.delta_pct * 100).toFixed(1)}%)`
              : '')
          : (j?.fundamentals === 'refreshed' || j?.fv != null)
            ? 'synced' : 'done',
      )
      setState('ok')
      router.refresh()
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'failed')
      setState('err')
    }
  }

  return (
    <button
      type="button"
      disabled={state === 'run'}
      onClick={sync}
      title="Sync fundamentals + FV — refetches the provider bundle, recomputes the flywheel, rescores fundamentals and re-resolves fair value (journaled, with the delta)"
      className={`inline-flex items-center gap-1 rounded-md border border-hairline px-2 py-0.5 text-[10px] font-medium tracking-wider transition-colors ${
        state === 'run'
          ? 'text-faint cursor-wait'
          : state === 'err'
            ? 'text-defensive border-defensive/40'
            : 'text-muted hover:text-ink hover:border-line cursor-pointer'
      }`}
    >
      <span className={state === 'run' ? 'animate-spin inline-block' : 'inline-block'}
        style={state === 'run' ? { animationDuration: '0.8s' } : undefined}>
        ⟳
      </span>
      {state === 'run' ? 'syncing' : 'sync'}
      {note && <span className="normal-case">· {note}</span>}
    </button>
  )
}
