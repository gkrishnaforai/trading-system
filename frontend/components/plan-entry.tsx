'use client'

import { useState } from 'react'

type Draft = {
  symbol: string
  use_case: string
  entry_px?: number | null
  stop_px?: number | null
  target1_px?: number | null
  target2_px?: number | null
}

/** One-click plan entry — binds the engine's suggested levels to a
 *  journaled trade_plans row. The trade itself is placed manually;
 *  this only opens the tracked plan. */
export function OpenPlanButton({
  draft, thesis, label,
}: {
  draft: Draft
  thesis?: string
  label?: string
}) {
  const [state, setState] = useState<'idle' | 'busy' | 'ok' | 'err'>('idle')
  const [msg, setMsg] = useState<string | null>(null)

  async function open() {
    setState('busy')
    setMsg(null)
    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'open', symbol: draft.symbol,
          use_case: draft.use_case,
          entry_px: draft.entry_px,
          stop_px: draft.stop_px, target1_px: draft.target1_px,
          target2_px: draft.target2_px,
          thesis: thesis ?? null,
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (res.ok && j?.ok) {
        setState('ok')
        setMsg(`plan #${j.id} open`)
      } else {
        setState('err')
        setMsg(String(j?.error ?? 'failed'))
      }
    } catch {
      setState('err')
      setMsg('unreachable')
    }
  }

  if (state === 'ok') {
    return (
      <span className="text-[11px] font-medium text-aggressive">
        ✓ {msg}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={open}
        disabled={state === 'busy'}
        className="rounded-full border border-accent/40 px-3 py-1 text-[11px] font-semibold text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
      >
        {state === 'busy' ? 'opening…' : label ?? 'open plan'}
      </button>
      {state === 'err' && (
        <span className="text-[11px] text-defensive">{msg}</span>
      )}
    </span>
  )
}

/** Close an open plan — journals close px + reason. */
export function ClosePlanButton({ id, px }: { id: number; px?: number | null }) {
  const [state, setState] = useState<'idle' | 'busy' | 'ok' | 'err'>('idle')
  const [pxIn, setPxIn] = useState(px != null ? String(px) : '')
  const [reason, setReason] = useState('')

  async function close() {
    setState('busy')
    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'close', id,
          close_px: pxIn ? Number(pxIn) : null,
          reason: reason || 'manual',
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (res.ok && j?.ok) {
        setState('ok')
        setTimeout(() => window.location.reload(), 800)
      } else {
        setState('err')
      }
    } catch {
      setState('err')
    }
  }

  if (state === 'ok') {
    return <span className="text-[11px] text-aggressive">✓ closed</span>
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        value={pxIn}
        onChange={(e) => setPxIn(e.target.value)}
        placeholder="close px"
        className="w-20 rounded border border-hairline bg-canvas px-2 py-0.5 font-mono text-[11px] text-ink"
      />
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="reason"
        className="w-28 rounded border border-hairline bg-canvas px-2 py-0.5 text-[11px] text-ink"
      />
      <button
        onClick={close}
        disabled={state === 'busy'}
        className="rounded-full border border-hairline px-2.5 py-0.5 text-[11px] text-muted hover:text-ink disabled:opacity-50"
      >
        {state === 'busy' ? '…' : 'close'}
      </button>
    </span>
  )
}
