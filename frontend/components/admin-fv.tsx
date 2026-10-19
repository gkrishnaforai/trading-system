'use client'

import { useEffect, useState } from 'react'

type Run = {
  sym: string
  status: 'queued' | 'running' | 'ok' | 'error'
  fv?: number
  expected?: number
  error?: string
}

type Portfolio = { id: string; name: string; holdings_count?: number }

/** Fair-value engine — batch recompute for admins. Pick a portfolio
    (holdings resolve to symbols) or run a single symbol. Sequential:
    each run is a real engine pass, ~seconds each; progress is honest. */
export default function AdminFv() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [selected, setSelected] = useState('')
  const [symbol, setSymbol] = useState('')
  const [force, setForce] = useState(true)
  const [runs, setRuns] = useState<Run[]>([])
  const [running, setRunning] = useState(false)

  useEffect(() => {
    fetch('/api/portfolio/portfolios', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : []))
      .then((j) => setPortfolios(Array.isArray(j) ? j : []))
      .catch(() => {})
  }, [])

  async function symbolsFor(id: string): Promise<string[]> {
    const res = await fetch(`/api/portfolio/portfolios/${id}/holdings`,
      { cache: 'no-store' })
    if (!res.ok) return []
    const rows = await res.json().catch(() => [])
    return (Array.isArray(rows) ? rows : [])
      .map((h: { symbol?: string }) => String(h.symbol ?? '').toUpperCase())
      .filter(Boolean)
  }

  async function runOne(sym: string) {
    try {
      const res = await fetch('/api/admin-fv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, force_refresh: force }),
      })
      const j = await res.json().catch(() => ({}))
      const r = j?.result ?? {}
      return {
        fv: r.fair_value != null ? Number(r.fair_value) : undefined,
        expected: r.expected_fair_value != null
          ? Number(r.expected_fair_value) : undefined,
        error: j?.success === false ? String(j.error ?? 'failed') : undefined,
      }
    } catch {
      return { error: 'unreachable' }
    }
  }

  async function start(syms: string[]) {
    if (!syms.length || running) return
    setRunning(true)
    const list: Run[] = syms.map((s) => ({ sym: s, status: 'queued' }))
    setRuns(list)
    for (let i = 0; i < list.length; i++) {
      setRuns((rs) => rs.map((r, j) =>
        j === i ? { ...r, status: 'running' } : r))
      const out = await runOne(list[i].sym)
      setRuns((rs) => rs.map((r, j) =>
        j === i
          ? { ...r, status: out.error ? 'error' : 'ok',
              fv: out.fv, expected: out.expected, error: out.error }
          : r))
    }
    setRunning(false)
  }

  const done = runs.filter((r) => r.status === 'ok' || r.status === 'error').length

  return (
    <div className="mt-8">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Fair value engine
          </div>
          <p className="pt-1 text-xs text-muted">
            recompute a portfolio — or a single symbol — persisting fresh
            runs every page reads
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <input type="checkbox" checked={force}
            onChange={(e) => setForce(e.target.checked)} />
          force refresh
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded-lg border border-hairline bg-elevated px-3 py-1.5 text-sm text-ink"
        >
          <option value="">choose portfolio…</option>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.holdings_count != null ? ` (${p.holdings_count})` : ''}
            </option>
          ))}
        </select>
        <button
          onClick={async () => start(await symbolsFor(selected))}
          disabled={!selected || running}
          className="rounded-lg border border-accent/40 px-3 py-1.5 text-sm text-accent hover:bg-accent/10 disabled:opacity-40"
        >
          ▶ run portfolio
        </button>
        <span className="text-faint text-xs">or</span>
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="SYMBOL"
          className="w-28 rounded-lg border border-hairline bg-elevated px-3 py-1.5 font-mono text-sm text-ink"
        />
        <button
          onClick={() => symbol && start([symbol])}
          disabled={!symbol || running}
          className="rounded-lg border border-hairline px-3 py-1.5 text-sm text-muted hover:text-ink disabled:opacity-40"
        >
          run one
        </button>
      </div>

      {runs.length > 0 && (
        <div className="mt-4">
          <div className="font-mono text-[11px] text-faint pb-1">
            {done}/{runs.length} done{running ? '…' : ''}
          </div>
          <div className="rounded-lg border border-hairline divide-y divide-hairline/60">
            {runs.map((r) => (
              <div key={r.sym}
                className="flex items-baseline justify-between px-3 py-1.5 text-sm">
                <span className="font-mono text-ink">{r.sym}</span>
                <span className="font-mono text-xs">
                  {r.status === 'running' && <span className="text-caution">running…</span>}
                  {r.status === 'queued' && <span className="text-faint">queued</span>}
                  {r.status === 'ok' && (
                    <span className="text-muted">
                      {r.expected != null && `exp $${r.expected.toFixed(2)} · `}
                      {r.fv != null ? `base $${r.fv.toFixed(2)}` : 'no fv'}
                    </span>
                  )}
                  {r.status === 'error' && (
                    <span className="text-defensive">{r.error ?? 'failed'}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
