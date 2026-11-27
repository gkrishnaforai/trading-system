'use client'

import { useEffect, useState } from 'react'

/** Brain — admin view of the intelligence layer: vitals (what it
    knows), today's inputs (what it ate), evolution (how it's moving),
    and the intake lane — submit a doc/news/URL and it runs the same
    verbatim-grounded pipeline as every other source, then journals
    accepted / partial / rejected with the why. */

type Why = {
  summary?: string
  basis?: { name?: string; value?: unknown; score?: unknown }[]
  counter?: string[]
  rule?: string
}

type IntakeRow = {
  id: number
  submitted_at?: string
  title?: string | null
  url?: string | null
  symbols?: string[]
  status?: string
  verdict?: Why | null
  landed?: Record<string, number>
  dropped?: { symbol?: string; reason?: string; claim?: string }[]
}

const STATUS_TONE: Record<string, string> = {
  accepted: 'bg-constructive/15 text-constructive',
  partial: 'bg-caution/15 text-caution',
  rejected: 'bg-defensive/15 text-defensive',
  error: 'bg-defensive/15 text-defensive',
  queued: 'bg-hairline/60 text-muted',
  processing: 'bg-accent/15 text-accent',
}

function ago(iso?: string) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000)
  if (s < 90) return `${Math.floor(s)}s ago`
  if (s < 5400) return `${Math.floor(s / 60)}m ago`
  if (s < 129600) return `${(s / 3600).toFixed(1)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

function et(iso?: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric',
    minute: '2-digit', timeZone: 'America/New_York',
  }) + ' ET'
}

function Count({ label, value, sub }: { label: string; value: unknown; sub?: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-faint">{label}</div>
      <div className="font-mono text-lg text-ink">{value == null ? '—' : String(value)}</div>
      {sub && <div className="text-[10px] text-faint">{sub}</div>}
    </div>
  )
}

function IntakeForm({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [symbols, setSymbols] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setResult(null)
    try {
      const res = await fetch('/api/brain', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ title, url, text, symbols }),
      })
      const r = await res.json()
      if (r.deduped) {
        setResult(`already in queue — status ${r.status}`)
      } else {
        const v = r.verdict?.summary
        setResult(`${r.status}${v ? ` — ${v}` : ''}`)
      }
      setTitle(''); setUrl(''); setText(''); setSymbols('')
      onDone()
    } catch (e) {
      setResult(`submit failed: ${String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-accent/40 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/10"
      >
        + feed the brain
      </button>
    )
  }
  return (
    <div className="rounded-xl border border-hairline bg-card p-4 space-y-2">
      <div className="flex gap-2">
        <input
          value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="title (optional)"
          className="flex-1 rounded-md border border-hairline bg-transparent px-2 py-1.5 text-xs text-ink placeholder:text-faint"
        />
        <input
          value={symbols} onChange={(e) => setSymbols(e.target.value)}
          placeholder="symbols (comma-sep, optional — auto-detects)"
          className="w-64 rounded-md border border-hairline bg-transparent px-2 py-1.5 text-xs text-ink placeholder:text-faint"
        />
      </div>
      <input
        value={url} onChange={(e) => setUrl(e.target.value)}
        placeholder="url (fetched if reachable — paywalled sources need pasted text)"
        className="w-full rounded-md border border-hairline bg-transparent px-2 py-1.5 text-xs text-ink placeholder:text-faint"
      />
      <textarea
        value={text} onChange={(e) => setText(e.target.value)}
        placeholder="paste the article/note text (≥200 chars)"
        rows={5}
        className="w-full rounded-md border border-hairline bg-transparent px-2 py-1.5 text-xs text-ink placeholder:text-faint"
      />
      <div className="flex items-center gap-3">
        <button
          onClick={submit}
          disabled={busy || (!text && !url)}
          className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-canvas disabled:opacity-40"
        >
          {busy ? 'processing…' : 'process'}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="text-xs text-muted hover:text-ink"
        >
          cancel
        </button>
        {result && <span className="text-[11px] text-muted">{result}</span>}
      </div>
      <p className="text-[10px] text-faint">
        every claim must carry a verbatim quote from the text — claims
        that can't be grounded are dropped, and if nothing lands the
        submission is rejected with the reason.
      </p>
    </div>
  )
}

function IntakeQueue({ rows }: { rows: IntakeRow[] }) {
  if (!rows.length) {
    return <p className="text-xs text-faint">no submissions yet</p>
  }
  return (
    <div className="divide-y divide-hairline/60">
      {rows.map((r) => (
        <div key={r.id} className="py-2.5">
          <div className="flex items-center gap-2 text-xs">
            <span className={`rounded-full px-2 py-0.5 font-medium ${STATUS_TONE[r.status ?? 'queued']}`}>
              {r.status}
            </span>
            <span className="font-medium text-ink truncate flex-1">
              {r.title || r.url || `#${r.id}`}
            </span>
            {(r.symbols ?? []).map((s) => (
              <span key={s} className="font-mono text-[10px] text-accent">{s}</span>
            ))}
            <span className="text-[10px] text-faint shrink-0">{ago(r.submitted_at)}</span>
          </div>
          {r.verdict?.summary && (
            <p className="pt-1 text-[11px] text-muted leading-snug">{r.verdict.summary}</p>
          )}
          {r.landed && Object.keys(r.landed).length > 0 && (
            <p className="pt-0.5 font-mono text-[10px] text-faint">
              landed: {Object.entries(r.landed)
                .filter(([, v]) => v > 0)
                .map(([k, v]) => `${k} ${v}`).join(' · ')}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

export default function BrainPage() {
  const [data, setData] = useState<Record<string, any> | null>(null)
  const [queue, setQueue] = useState<IntakeRow[]>([])

  async function load() {
    const [d, q] = await Promise.all([
      fetch('/api/brain', { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
      fetch('/api/brain?part=queue', { cache: 'no-store' }).then((r) => r.json()).catch(() => null),
    ])
    setData(d)
    setQueue(q?.queue ?? [])
  }
  useEffect(() => { load() }, [])

  const v = data?.vitals ?? {}
  const today = data?.today ?? {}
  const evo = data?.evolution ?? {}
  const stages = v.themes?.by_stage ?? {}
  const claimSt = v.claims?.by_status ?? {}
  const jobs: Record<string, any>[] = today.jobs ?? []

  return (
    <main className="mx-auto max-w-3xl px-5 pb-16">
      <header className="pt-8 pb-6">
        <h1 className="text-xl font-semibold text-ink">
          Brain <span className="text-accent">·</span>{' '}
          <span className="text-sm font-normal text-muted">
            the intelligence layer — vitals, inputs, evolution, intake
          </span>
        </h1>
      </header>

      {/* ---------- vitals ---------- */}
      <section className="rounded-xl border border-hairline bg-card px-5 py-4">
        <h2 className="text-[10px] uppercase tracking-wider text-faint pb-3">
          what it knows
        </h2>
        <div className="grid grid-cols-3 gap-4 md:grid-cols-6">
          <Count label="themes" value={Object.values(stages).reduce<number>((a, b) => a + (b as number), 0) || '—'}
            sub={Object.entries(stages).map(([k, n]) => `${k} ${n}`).join(' · ')} />
          <Count label="claims" value={v.claims?.total}
            sub={Object.entries(claimSt).map(([k, n]) => `${k} ${n}`).join(' · ')} />
          <Count label="edges" value={v.edges} />
          <Count label="forecasts" value={v.forecasts?.driver_forecasts}
            sub={`${v.forecasts?.graded_kinds ?? 0} kinds graded`} />
          <Count label="docs" value={v.docs?.analyzed}
            sub={`${v.docs?.watches_open ?? 0} watches open`} />
          <Count label="evidence" value={v.evidence} />
        </div>
      </section>

      {/* ---------- today's inputs ---------- */}
      <section className="pt-6">
        <h2 className="text-[10px] uppercase tracking-wider text-faint pb-2">
          today's inputs
        </h2>
        <div className="rounded-xl border border-hairline bg-card px-5 py-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 pb-2 text-[11px] text-muted">
            <span>claims emitted <b className="font-mono text-ink">{today.claims_emitted ?? 0}</b></span>
            <span>docs analyzed <b className="font-mono text-ink">{today.docs_analyzed ?? 0}</b></span>
            <span>evidence rows <b className="font-mono text-ink">{today.evidence_rows ?? 0}</b></span>
            <span>intake items <b className="font-mono text-ink">{today.intake ?? 0}</b></span>
            <span>jobs run <b className="font-mono text-ink">{jobs.length}</b></span>
          </div>
          <div className="divide-y divide-hairline/40">
            {jobs.map((j, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5 text-[11px]">
                <span className={`w-1.5 h-1.5 rounded-full ${j.error ? 'bg-defensive' : 'bg-constructive'}`} />
                <span className="font-mono text-ink w-44 truncate">{j.name}</span>
                <span className="text-faint">{j.ran_at ? et(j.ran_at) : ''}</span>
                {j.error && <span className="text-defensive truncate flex-1">{String(j.error).slice(0, 80)}</span>}
              </div>
            ))}
            {!jobs.length && (
              <p className="py-2 text-[11px] text-faint">no jobs have run today</p>
            )}
          </div>
        </div>
      </section>

      {/* ---------- evolution ---------- */}
      <section className="pt-6">
        <h2 className="text-[10px] uppercase tracking-wider text-faint pb-2">
          how it's moving — last 30d
        </h2>
        <div className="rounded-xl border border-hairline bg-card px-5 py-3 space-y-3">
          {(evo.promotions ?? []).length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-faint pb-1">promoted</div>
              {(evo.promotions ?? []).map((p: Record<string, any>) => (
                <div key={p.theme_key} className="text-[11px] py-0.5">
                  <span className="text-ink font-medium">{p.name}</span>{' '}
                  <span className="text-constructive">{p.stage}</span>{' '}
                  <span className="text-faint">{p.promoted_at}</span>
                </div>
              ))}
            </div>
          )}
          {(evo.restaged ?? []).length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-faint pb-1">re-staged on review</div>
              {(evo.restaged ?? []).map((p: Record<string, any>) => (
                <div key={p.theme_key} className="text-[11px] py-0.5">
                  <span className="text-ink font-medium">{p.name}</span>{' '}
                  <span className="text-caution">{p.stage}</span>{' '}
                  <span className="text-faint">{p.last_review}</span>
                </div>
              ))}
            </div>
          )}
          {(evo.claim_moves ?? []).length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-faint pb-1">claim moves (7d)</div>
              {(evo.claim_moves ?? []).slice(0, 10).map((c: Record<string, any>, i: number) => (
                <div key={i} className="text-[11px] py-0.5 flex gap-2">
                  <span className="font-mono text-faint w-20 shrink-0">{c.review_kind}</span>
                  <span className="font-mono text-accent w-28 truncate shrink-0">{c.claim_id}</span>
                  <span className="text-muted truncate">{c.verdict}</span>
                  <span className="text-faint shrink-0">{ago(c.created_at)}</span>
                </div>
              ))}
            </div>
          )}
          {!(evo.promotions ?? []).length && !(evo.restaged ?? []).length && !(evo.claim_moves ?? []).length && (
            <p className="text-[11px] text-faint">no movement journaled recently</p>
          )}
        </div>
      </section>

      {/* ---------- intake ---------- */}
      <section className="pt-6">
        <div className="flex items-center justify-between pb-2">
          <h2 className="text-[10px] uppercase tracking-wider text-faint">
            intake — feed it, it decides
          </h2>
          <IntakeForm onDone={load} />
        </div>
        <div className="rounded-xl border border-hairline bg-card px-5 py-2">
          <IntakeQueue rows={queue} />
        </div>
      </section>
    </main>
  )
}
