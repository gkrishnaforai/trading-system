'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

/** Row actions for the ops catalog — run-now, enable toggle, inline
    cron edit. All mutations go through the role-gated /api/admin
    proxy; the dispatcher only honors set_schedule writes. */
export function JobActions({
  name, enabled, cron,
}: { name: string; enabled: boolean; cron: string | null }) {
  const router = useRouter()
  const [busy, setBusy] = useState<string | null>(null)
  const [editCron, setEditCron] = useState<string | null>(null)
  const [draft, setDraft] = useState(cron ?? '')
  const [msg, setMsg] = useState<string | null>(null)

  async function act(key: string, fn: () => Promise<Response>) {
    setBusy(key)
    setMsg(null)
    try {
      const res = await fn()
      const j = await res.json().catch(() => ({}))
      if (!res.ok || j?.ok === false) {
        setMsg(j?.error ?? j?.detail ?? `error ${res.status}`)
      }
      router.refresh()
    } catch {
      setMsg('worker unreachable')
    } finally {
      setBusy(null)
    }
  }

  const run = () => act('run', () =>
    fetch(`/api/admin/refresh/${encodeURIComponent(name)}`, { method: 'POST' }))
  const toggle = () => act('toggle', () =>
    fetch(`/api/admin/jobs/${encodeURIComponent(name)}/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cron, enabled: !enabled }),
    }))
  const saveCron = () => act('cron', async () => {
    const res = await fetch(`/api/admin/jobs/${encodeURIComponent(name)}/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cron: draft || null, enabled }),
    })
    if (res.ok) setEditCron(null)
    return res
  })

  return (
    <span className="flex flex-wrap items-center justify-end gap-1.5">
      {editCron == null ? (
        <button
          onClick={() => { setEditCron(name); setDraft(cron ?? '') }}
          className="rounded-md border border-hairline px-2 py-1 text-[11px] text-muted hover:text-ink hover:border-faint transition-colors"
        >
          {cron ? 'edit cron' : 'set cron'}
        </button>
      ) : (
        <span className="flex items-center gap-1">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="m h dom mon dow"
            className="w-32 rounded-md border border-hairline bg-canvas px-2 py-1 font-mono text-[11px] text-ink outline-none focus:border-accent"
          />
          <button
            onClick={saveCron}
            disabled={busy === 'cron'}
            className="rounded-md border border-accent px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/10 disabled:opacity-40"
          >
            save
          </button>
          <button
            onClick={() => setEditCron(null)}
            className="px-1.5 py-1 text-[11px] text-faint hover:text-ink"
          >
            ✕
          </button>
        </span>
      )}
      <button
        onClick={toggle}
        disabled={busy === 'toggle'}
        className={`rounded-md border px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-40 ${enabled
            ? 'border-hairline text-muted hover:border-caution hover:text-caution'
            : 'border-hairline text-muted hover:border-aggressive hover:text-aggressive'
          }`}
      >
        {enabled ? 'pause' : 'enable'}
      </button>
      <button
        onClick={run}
        disabled={busy === 'run'}
        className="rounded-md border border-accent px-2.5 py-1 text-[11px] font-semibold text-accent hover:bg-accent/10 disabled:opacity-40 transition-colors"
      >
        {busy === 'run' ? 'kicked…' : '▶ run'}
      </button>
      {msg && <span className="w-full text-right text-[10px] text-defensive">{msg}</span>}
    </span>
  )
}

/** The box job — refresh everything in dependency order. */
export function RunAll() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  return (
    <button
      onClick={async () => {
        setBusy(true)
        try {
          await fetch('/api/admin/refresh/all', { method: 'POST' })
          router.refresh()
        } finally {
          setBusy(false)
        }
      }}
      disabled={busy}
      className="rounded-lg border border-accent bg-accent/5 px-4 py-2 text-xs font-semibold text-accent hover:bg-accent/10 disabled:opacity-40 transition-colors"
    >
      {busy ? 'kicked…' : '▶ run everything'}
    </button>
  )
}
