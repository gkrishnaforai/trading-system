'use client'

import { useState } from 'react'

type Row = {
  symbol: string; signal: string; score?: number | null
  vwap_hold_min?: number | null; rs30_smh?: number | null
  rvol?: number | null; delta_vol?: number | null
  recovery_score?: number | null; accumulation_score?: number | null
  overextended?: boolean | null; ext_pct?: number | null
}

type Session = {
  gap_pct?: number | null
  bars?: { ts: string; c?: number | null; v?: number | null }[]
  vwap?: number[]
  evals?: { ts: string; signal: string; score?: number | null }[]
  transitions?: { ts: string; from: string; to: string }[]
}

const SIG_COLOR: Record<string, string> = {
  STRONG_RECOVERY: 'text-aggressive',
  CONFIRMED_RECOVERY: 'text-aggressive/80',
  IMPROVING: 'text-caution',
  WATCH: 'text-faint',
  DISTRIBUTION: 'text-defensive',
  FAILED_REBOUND: 'text-defensive',
  DATA_BLOCKED: 'text-faint',
}
const SIG_BG: Record<string, string> = {
  STRONG_RECOVERY: 'bg-aggressive',
  CONFIRMED_RECOVERY: 'bg-aggressive/70',
  IMPROVING: 'bg-caution',
  WATCH: 'bg-line',
  DISTRIBUTION: 'bg-defensive',
  FAILED_REBOUND: 'bg-defensive/70',
  DATA_BLOCKED: 'bg-hairline',
}

function et(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: 'numeric', minute: '2-digit',
      timeZone: 'America/New_York' })
  } catch { return ts.slice(11, 16) }
}

function SessionView({ s }: { s: Session }) {
  const bars = s.bars ?? []
  const closes = bars.map(b => b.c).filter((x): x is number => x != null)
  const vw = (s.vwap ?? []).filter((x): x is number => x != null)
  if (closes.length < 3) {
    return <p className="py-2 text-[11px] text-faint">no session bars</p>
  }
  const w = 720, h = 64, pad = 4
  const all = [...closes, ...vw]
  const lo = Math.min(...all), hi = Math.max(...all)
  const span = hi - lo || 1
  const x = (i: number, n: number) =>
    pad + (i / Math.max(1, n - 1)) * (w - 2 * pad)
  const y = (v: number) => h - pad - ((v - lo) / span) * (h - 2 * pad)
  const price = closes.map((c, i) =>
    `${x(i, closes.length).toFixed(1)},${y(c).toFixed(1)}`).join(' ')
  const vwap = vw.map((c, i) =>
    `${x(i, vw.length).toFixed(1)},${y(c).toFixed(1)}`).join(' ')
  const evals = s.evals ?? []
  const stripW = evals.length > 0 ? (w - 2 * pad) / evals.length : 0
  return (
    <div className="py-2">
      <svg viewBox={`0 0 ${w} ${h + 10}`} className="h-20 w-full"
        preserveAspectRatio="none" role="img"
        aria-label="session price vs vwap">
        {vw.length > 1 && (
          <polyline points={vwap} fill="none" stroke="#A8A29E"
            strokeWidth="1" strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke" />
        )}
        <polyline points={price} fill="none" stroke="#78716C"
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <circle cx={x(closes.length - 1, closes.length)} r="3"
          cy={y(closes[closes.length - 1])} fill="#EA580C" />
        {evals.map((e, i) => (
          <rect key={i}
            x={x(i, Math.max(1, evals.length))}
            y={h + 1} width={Math.max(1, stripW - 0.5)} height={6}
            className={SIG_BG[e.signal] ?? 'bg-hairline'} />
        ))}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 pt-1 font-mono
                      text-[10px] text-faint">
        {s.gap_pct != null &&
          <span>gap {s.gap_pct > 0 ? '+' : ''}{s.gap_pct}%</span>}
        <span>price — · vwap - - · strip = signal per 5m bar</span>
        {(s.transitions ?? []).map((t, i) => (
          <span key={i}>
            {et(t.ts)} {t.from.replace(/_/g, ' ').toLowerCase()}
            {' → '}{t.to.replace(/_/g, ' ').toLowerCase()}
          </span>
        ))}
      </div>
    </div>
  )
}

export function RecoveryPanel({ rows, asOf, stale, participation }: {
  rows: Row[]; asOf?: string | null; stale?: boolean | null
  participation?: number | null
}) {
  const [open, setOpen] = useState<string | null>(null)
  const [data, setData] = useState<Record<string, Session>>({})
  const [loading, setLoading] = useState<string | null>(null)

  async function toggle(sym: string) {
    if (open === sym) { setOpen(null); return }
    setOpen(sym)
    if (data[sym]) return
    setLoading(sym)
    try {
      const r = await fetch(`/api/ire-session/${sym}`)
      if (r.ok) {
        const j = await r.json()
        setData(d => ({ ...d, [sym]: j }))
      }
    } catch { /* session stays unexpanded */ }
    setLoading(null)
  }

  if (!rows.length) return null
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2 pb-2">
        <h2 className="text-sm font-semibold tracking-wide text-ink">
          AI-infra recovery — vwap confirmation
        </h2>
        <div className="font-mono text-[11px] text-faint">
          {asOf
            ? new Date(asOf).toLocaleTimeString('en-US', {
                hour: 'numeric', minute: '2-digit',
                timeZone: 'America/New_York' }) + ' ET'
            : ''}
          {stale ? ' · stale' : ''}
          {participation != null &&
            ` · ${Math.round(participation)}% of universe above vwap`}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <tbody>
            {rows.slice(0, 20).map((r) => {
              const sig = r.signal ?? 'WATCH'
              const cls = SIG_COLOR[sig] ?? 'text-faint'
              const expanded = open === r.symbol
              return (
                <FragmentRow key={r.symbol}>
                  <tr onClick={() => toggle(r.symbol)}
                    className="cursor-pointer border-t border-hairline/40
                               hover:bg-line/20">
                    <td className="py-1 pr-3 font-medium">
                      <span className="text-faint">{expanded ? '▾ ' : '▸ '}</span>
                      {r.symbol}
                    </td>
                    <td className={`py-1 pr-3 font-mono ${cls}`}>
                      {sig.replace(/_/g, ' ').toLowerCase()}
                      {r.overextended ? ' ⚠' : ''}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted">
                      {r.score ?? '—'}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted"
                      title="price recovery — vwap hold + structure + opening range">
                      rec {r.recovery_score ?? '—'}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted"
                      title="accumulation — rs + directional volume + rvol + breadth">
                      accum {r.accumulation_score ?? '—'}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted">
                      vwap {r.vwap_hold_min != null
                        ? `${r.vwap_hold_min}m` : '—'}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted">
                      rs {r.rs30_smh != null
                        ? `${r.rs30_smh > 0 ? '+' : ''}${Number(r.rs30_smh).toFixed(1)}` : '—'}
                    </td>
                    <td className="py-1 pr-3 font-mono text-muted">
                      rvol {r.rvol != null ? `${r.rvol}x` : '—'}
                    </td>
                    <td className="py-1 font-mono text-muted">
                      {r.delta_vol != null &&
                        `Δvol ${r.delta_vol > 0 ? '+' : ''}${r.delta_vol}`}
                      {(r.ext_pct ?? 0) > 3
                        ? ` · +${Number(r.ext_pct).toFixed(1)}% ext`
                        : ''}
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="border-t border-hairline/20">
                      <td colSpan={9} className="px-2 pb-2">
                        {loading === r.symbol
                          ? <p className="py-2 text-[11px] text-faint">loading…</p>
                          : data[r.symbol]
                            ? <SessionView s={data[r.symbol]} />
                            : <p className="py-2 text-[11px] text-faint">no session data</p>}
                      </td>
                    </tr>
                  )}
                </FragmentRow>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
