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

export function ResilienceClient({ rows }: { rows: ResilienceRow[] }) {
  const [sortKey, setSortKey] = useState<Key>('ai_opportunity')
  const [q, setQ] = useState('')
  const sorted = useMemo(() => {
    const f = rows.filter(r => !q
      || r.symbol.toLowerCase().includes(q.toLowerCase())
      || (r.business_model ?? '').toLowerCase().includes(q.toLowerCase()))
    return [...f].sort((a, b) =>
      (b.scores?.[sortKey] ?? -1) - (a.scores?.[sortKey] ?? -1))
  }, [rows, sortKey, q])
  return (
    <div className="mt-5">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-[0.18em] text-muted">
          Company scores — health · ai · tape
        </div>
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="search symbol / model"
          className="rounded border border-line/60 bg-transparent px-2 py-0.5 text-[11px] text-ink placeholder:text-faint focus:outline-none"
        />
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
                  <td className="py-1.5 pr-3 font-medium">{sc.ai_opportunity ?? '—'}</td>
                  <td className="py-1.5 pr-3">{sc.company_health ?? '—'}</td>
                  <td className="py-1.5 pr-3">{sc.tape_resilience ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-muted">{sc.deployment_risk ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-muted">{(r.business_model ?? '').replaceAll('_', ' ')}</td>
                  <td className="py-1.5 text-muted">{meta.slice(0, 3).join(' · ') || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-1 text-[10px] text-faint">
        {sorted.length} scored — click a column header to sort
      </div>
    </div>
  )
}
