'use client'

import { useEffect, useState } from 'react'

/** Research run controls — fire the board job or a single symbol,
 *  and edit the job's cron schedule. Writes go through the
 *  admin-gated /api/admin proxy; a 403 just reports 'admin
 *  access required' rather than pretending the run happened. */

export function ResearchControls() {
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [sym, setSym] = useState('')
  const [cron, setCron] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [nextRun, setNextRun] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/admin/jobs/catalog')
      .then((r) => r.json())
      .then((d) => {
        const j = (d.jobs || []).find(
          (x: { name?: string }) => x.name === 'research')
        if (j) {
          setCron(j.cron || '')
          setEnabled(Boolean(j.enabled))
          setNextRun(j.next_run)
          setLastRun(j.last_run)
        }
      })
      .catch(() => {})
  }, [])

  async function post(path: string, body?: unknown) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.error || `${res.status}`)
    return data
  }

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key)
    setMsg('')
    try {
      const d = (await fn()) as { status?: string; report?: { recommendation?: { action?: string } } }
      setMsg(d.report?.recommendation?.action
        ? `done → ${d.report.recommendation.action}`
        : d.status || 'done')
    } catch (e) {
      setMsg(String(e instanceof Error ? e.message : e))
    } finally {
      setBusy(null)
    }
  }

  const btn =
    'rounded border border-hairline px-2.5 py-1 text-xs text-muted hover:text-ink hover:border-muted transition-colors disabled:opacity-40'

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-hairline bg-card px-4 py-3">
      <button
        className={btn}
        disabled={busy !== null}
        onClick={() => act('all', () => post('/api/admin/refresh/research'))}
      >
        {busy === 'all' ? 'starting…' : 'run board now'}
      </button>
      <span className="text-faint">or</span>
      <input
        value={sym}
        onChange={(e) => setSym(e.target.value.toUpperCase())}
        placeholder="SYM"
        maxLength={6}
        className="w-20 rounded border border-hairline bg-canvas px-2 py-1 text-xs font-mono text-ink placeholder:text-faint focus:border-accent focus:outline-none"
      />
      <button
        className={btn}
        disabled={busy !== null || !sym.trim()}
        onClick={() =>
          act('one', () =>
            post(`/api/admin/research/${encodeURIComponent(sym.trim())}`))}
      >
        {busy === 'one' ? 'running…' : 'run symbol'}
      </button>

      <span className="mx-1 h-4 w-px bg-hairline" />

      <label className="flex items-center gap-1.5 text-[11px] text-faint">
        schedule (UTC cron)
        <input
          value={cron}
          onChange={(e) => setCron(e.target.value)}
          placeholder="30 14 * * 0"
          className="w-32 rounded border border-hairline bg-canvas px-2 py-1 text-xs font-mono text-ink placeholder:text-faint focus:border-accent focus:outline-none"
        />
      </label>
      <label className="flex items-center gap-1 text-[11px] text-faint">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="accent-accent"
        />
        on
      </label>
      <button
        className={btn}
        disabled={busy !== null}
        onClick={() =>
          act('sched', () =>
            post('/api/admin/jobs/research/schedule',
              { cron: cron.trim() || null, enabled }))}
      >
        {busy === 'sched' ? 'saving…' : 'save'}
      </button>
      {nextRun && enabled && (
        <span className="text-[10px] text-faint">
          next {new Date(nextRun).toLocaleString()}
        </span>
      )}
      {lastRun && (
        <span className="text-[10px] text-faint">
          last {new Date(lastRun).toLocaleString()}
        </span>
      )}
      {msg && (
        <span className="basis-full pt-1 text-[11px] text-caution">{msg}</span>
      )}
    </div>
  )
}
