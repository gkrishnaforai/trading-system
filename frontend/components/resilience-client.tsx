'use client'
import { useMemo, useState } from 'react'
import type { ResilienceRow } from '@/lib/api'

type Key = 'ai_opportunity' | 'company_health' | 'tape_resilience' | 'deployment_risk'
const COLS: { k: Key; label: string }[] = [
  { k: 'ai_opportunity', label: 'ai' },
  { k: 'company_health', label: 'hlth' },
  { k: 'tape_resilience', label: 'tape' },
  { k: 'deployment_risk', label: 'dep' },
]

function Delta({ d }: { d?: number | null }) {
  if (d == null || d === 0) return null
  const up = d > 0
  return (
    <span className={`pl-1 text-[10px] ${up ? 'text-aggressive' : 'text-defensive'}`}>
      {up ? '▲' : '▼'}{Math.abs(d)}
    </span>
  )
}

// today-filters — every predicate reads the 15-min live overlay, never
// the weekly journal, so a name lands in the right bucket intraday.
// Rows without live ticks fail every filter (missing ≠ passing).
const FILTERS: { k: string; label: string;
                 test: (r: ResilienceRow) => boolean }[] = [
  { k: 'green', label: '▲ today',
    test: r => (r.tape_live?.rel1 ?? 0) > 0 },
  { k: 'red', label: '▼ today',
    test: r => (r.tape_live?.rel1 ?? 0) < 0 },
  { k: 'healing', label: 'healing',
    // live tape ≥5 pts above the last journal — the snapshot caught the
    // wound, the tape has been out-performing since
    test: r => r.tape_live?.tape_live != null
            && r.scores?.tape_resilience != null
            && r.tape_live.tape_live
               >= (r.scores.tape_resilience ?? 0) + 5 },
  { k: 'turning', label: 'turning',
    // the live dip read says the selloff is resolving — the watch
    // bucket for swing setups
    test: r => ['turning_up', 'confirmed']
      .includes(r.swing_live?.dip_phase_live ?? '') },
]

export function ResilienceClient({ rows }: { rows: ResilienceRow[] }) {
  const [sortKey, setSortKey] = useState<Key>('ai_opportunity')
  const [q, setQ] = useState('')
  const [active, setActive] = useState<Set<string>>(new Set())
  const toggle = (k: string) =>
    setActive(prev => {
      const n = new Set(prev)
      if (n.has(k)) n.delete(k); else n.add(k)
      return n
    })
  const counts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const f of FILTERS)
      m[f.k] = rows.filter(f.test).length
    return m
  }, [rows])
  const sorted = useMemo(() => {
    const f = rows.filter(r => {
      if (q && !r.symbol.toLowerCase().includes(q.toLowerCase())
          && !(r.business_model ?? '').toLowerCase()
              .includes(q.toLowerCase())) return false
      for (const k of active) {
        const flt = FILTERS.find(x => x.k === k)
        if (flt && !flt.test(r)) return false
      }
      return true
    })
    return [...f].sort((a, b) =>
      (b.scores?.[sortKey] ?? -1) - (a.scores?.[sortKey] ?? -1))
  }, [rows, sortKey, q, active])
  return (
    <div className="mt-5">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-[0.18em] text-muted">
          Company scores — health · ai · tape
          {(() => {
            const live = rows
              .map((r) => r.tape_live?.as_of)
              .filter(Boolean)
              .sort()
              .pop()
            return live ? (
              <span className="ml-2 font-mono text-[10px] normal-case tracking-normal text-accent">
                · live bars {new Date(String(live)).toLocaleTimeString('en-US',
                    { hour: 'numeric', minute: '2-digit',
                      timeZone: 'America/New_York' })} ET
              </span>
            ) : null
          })()}
        </div>
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="search symbol / model"
          className="rounded border border-line/60 bg-transparent px-2 py-0.5 text-[11px] text-ink placeholder:text-faint focus:outline-none"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {FILTERS.map(f => {
          const on = active.has(f.k)
          return (
            <button
              key={f.k}
              onClick={() => toggle(f.k)}
              className={`rounded border px-1.5 py-px font-mono text-[10px] transition-colors ${
                on
                  ? 'border-accent/60 bg-accent/10 text-accent'
                  : 'border-line/60 text-muted hover:text-ink'
              }`}
              title={
                f.k === 'green' ? 'outperforming SPY today (live rel-1d > 0)'
                : f.k === 'red' ? 'underperforming SPY today (live rel-1d < 0)'
                : f.k === 'healing' ? 'live tape ≥5 pts above last journal — recovering names'
                : 'live dip phase turning_up / confirmed — selloff resolving'
              }
            >
              {f.label} {counts[f.k] ?? 0}
            </button>
          )
        })}
        {active.size > 0 && (
          <button
            onClick={() => setActive(new Set())}
            className="px-1 text-[10px] text-faint hover:text-ink"
          >
            clear
          </button>
        )}
      </div>
      <div className="mt-2 max-h-[480px] overflow-y-auto overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-base">
            <tr className="text-left text-muted">
              <th className="py-1 pr-3 font-medium">sym</th>
              {COLS.map(c => (
                <th key={c.k} className="py-1 pr-3 font-medium">
                  <button
                    onClick={() => setSortKey(c.k)}
                    className={sortKey === c.k ? 'text-ink underline underline-offset-2' : 'hover:text-ink'}>
                    {c.label}{sortKey === c.k ? ' ↓' : ''}
                  </button>
                </th>
              ))}
              <th className="py-1 pr-3 font-medium">flow</th>
              <th className="py-1 pr-3 font-medium">model</th>
              <th className="py-1 font-medium">flags / needs</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => {
              const sc = r.scores ?? {}
              const meta = [...(r.flags ?? []), ...(r.needs ?? []).map((n: string) => `needs: ${n}`)]
              return (
                <tr key={r.symbol} className="border-t border-line/40">
                  <td className="py-1.5 pr-3 font-medium text-ink">
                    <a href={`/stock?symbol=${r.symbol}`}>{r.symbol}</a>
                  </td>
                  <td className="py-1.5 pr-3 font-medium">
                    {sc.ai_opportunity ?? '—'}<Delta d={r.delta?.ai_opportunity} />
                  </td>
                  <td className="py-1.5 pr-3">
                    {sc.company_health ?? '—'}<Delta d={r.delta?.company_health} />
                  </td>
                  <td className="py-1.5 pr-3">
                    {sc.tape_resilience ?? '—'}<Delta d={r.delta?.tape_resilience} />
                    {r.tape_live?.tape_live != null && (
                      <span className="text-accent" title={`live ${r.tape_live.as_of ?? ''} · today ${((r.tape_live.rel1 ?? 0) * 100).toFixed(1)}% vs SPY`}>
                        {' →'}{r.tape_live.tape_live}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-muted">{sc.deployment_risk ?? '—'}</td>
                  <td className="py-1.5 pr-3">{r.flow?.footprint === 'accumulating'
                    ? <span className="text-aggressive">▲ acc {r.flow.streak}d</span>
                    : r.flow?.footprint === 'distributing'
                      ? <span className="text-defensive">▼ dist {Math.abs(r.flow.streak ?? 0)}d</span>
                      : <span className="text-faint">—</span>}</td>
                  <td className="py-1.5 pr-3 text-muted">{(r.business_model ?? '').replaceAll('_', ' ')}</td>
                  <td className="py-1.5 text-muted">{meta.slice(0, 3).join(' · ') || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-1 text-[10px] text-faint">
        {active.size ? `${sorted.length} of ${rows.length}` : sorted.length}
        {' '}scored — click a column header to sort
      </div>
    </div>
  )
}
