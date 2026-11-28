import Link from 'next/link'
import type { HealthRow } from '@/lib/api'
import { scoreHealthTone } from '@/components/deck'

/** Equity-health positions table — the SEC-data twin of
    PortfolioTable. Each row: holding + latest company-health read
    (score, trend, verdict, coverage, category legs, red flags).
    No price, no P&L — links resolve to the fundamentals page. */

const TREND_TONE: Record<string, string> = {
  improving: 'text-aggressive border-aggressive/30 bg-aggressive/10',
  stable: 'text-constructive border-constructive/30 bg-constructive/10',
  deteriorating:
    'text-defensive border-defensive/30 bg-defensive/10',
  new: 'text-muted border-hairline bg-elevated/60',
}

const EWF_GLYPH: Record<string, string> = {
  GREEN: 'text-aggressive', YELLOW: 'text-caution',
  RED: 'text-defensive',
}

function scoreChip(s?: number | null, verdict?: string) {
  if (verdict === 'insufficient_data')
    return (
      <span
        className="rounded-full border border-hairline bg-elevated/60 px-2 py-0.5 font-mono text-[10px] text-faint"
        title="coverage below the publish gate — category scores only"
      >
        n/a
      </span>
    )
  const n = Number(s)
  if (!Number.isFinite(n)) return <span className="text-faint">—</span>
  return (
    <span className={`font-mono text-sm font-semibold ${scoreHealthTone(n)}`}>
      {n}
    </span>
  )
}

function coverageBar(c?: number | null) {
  const n = Number(c)
  if (!Number.isFinite(n)) return <span className="text-faint">—</span>
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1 w-14 overflow-hidden rounded-full bg-elevated">
        <span
          className="block h-full bg-accent/70"
          style={{ width: `${Math.min(100, Math.max(0, n))}%` }}
        />
      </span>
      <span className="font-mono text-[10px] text-muted">
        {n.toFixed(0)}%
      </span>
    </span>
  )
}

function cats(row: HealthRow) {
  const cs = row.category_scores
  if (!cs) return null
  const entries = Object.entries(cs)
    .filter(([, v]) => v && v.score != null)
    .sort((a, b) => Number(b[1].weight ?? 0) - Number(a[1].weight ?? 0))
    .slice(0, 4)
  return (
    <span className="flex flex-wrap gap-x-2.5 gap-y-0.5">
      {entries.map(([k, v]) => (
        <span key={k} className="font-mono text-[10px] text-muted">
          <span className="text-faint">{k.slice(0, 9)}</span>{' '}
          <span className={scoreHealthTone(v.score)}>{v.score}</span>
        </span>
      ))}
    </span>
  )
}

export function HealthTable({
  rows, shares,
}: {
  rows: HealthRow[]
  shares?: Record<string, number | undefined>
}) {
  const cellCls =
    'px-3 py-2.5 font-mono text-xs text-muted whitespace-nowrap'
  const headCls =
    'px-3 py-2 text-left font-sans text-[10px] font-medium ' +
    'uppercase tracking-wider text-faint whitespace-nowrap select-none'

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-hairline">
            <th className={headCls}>Symbol</th>
            {shares && <th className={`${headCls} text-right`}>Shares</th>}
            <th className={`${headCls} text-right`}>Health</th>
            <th className={`${headCls} text-right`}>Δ</th>
            <th className={headCls}>Trend</th>
            <th className={headCls}>Coverage</th>
            <th className={headCls}>Categories</th>
            <th className={headCls}>Flags</th>
            <th className={`${headCls} text-right`}>Period</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const sym = String(r.symbol ?? '')
            const flags = (r.red_flags ?? []).length
            return (
              <tr key={sym + String(r.period_end)}
                className="border-b border-hairline/50 align-top">
                <td className={cellCls}>
                  <Link
                    href={`/equity?sym=${encodeURIComponent(sym)}`}
                    className="font-semibold text-ink hover:text-accent"
                  >
                    {sym}
                  </Link>
                  {r.ewf_state && (
                    <span
                      className={`ml-1.5 text-[10px] ${EWF_GLYPH[r.ewf_state] ?? 'text-faint'}`}
                      title={`early-warning: ${r.ewf_state}`}
                    >
                      ●
                    </span>
                  )}
                </td>
                {shares && (
                  <td className={`${cellCls} text-right`}>
                    {shares[sym] != null
                      ? Number(shares[sym]).toLocaleString('en-US',
                        { maximumFractionDigits: 4 })
                      : '—'}
                  </td>
                )}
                <td className={`${cellCls} text-right`}>
                  {scoreChip(r.score, r.verdict)}
                </td>
                <td className={`${cellCls} text-right`}>
                  {r.score_delta != null ? (
                    <span className={scoreDeltaTone(r.score_delta)}>
                      {r.score_delta > 0 ? '+' : ''}{r.score_delta}
                    </span>
                  ) : '—'}
                </td>
                <td className={cellCls}>
                  {r.trend ? (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${TREND_TONE[r.trend] ?? 'text-muted border-hairline'}`}
                    >
                      {r.trend}
                    </span>
                  ) : '—'}
                </td>
                <td className={cellCls}>{coverageBar(r.coverage_pct)}</td>
                <td className={`${cellCls} whitespace-normal`}>
                  {cats(r) ?? <span className="text-faint">—</span>}
                </td>
                <td className={cellCls}>
                  {flags > 0 ? (
                    <span className="text-defensive font-semibold"
                      title={(r.red_flags ?? [])
                        .map((f) => String(f.pattern ?? f.class ?? ''))
                        .join(' · ')}>
                      ⚑ {flags}
                    </span>
                  ) : <span className="text-faint">—</span>}
                </td>
                <td className={`${cellCls} text-right text-faint`}>
                  {r.period_end ? String(r.period_end).slice(0, 10) : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function scoreDeltaTone(d: number) {
  return d > 0 ? 'text-aggressive' : d < 0 ? 'text-defensive' : 'text-muted'
}
