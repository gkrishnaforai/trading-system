'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { CycleRow, CycleHistoryRow } from '@/lib/api'

const DEC_TONE: Record<string, string> = {
  accumulate: 'bg-aggressive/15 text-aggressive',
  add_on_pullback: 'bg-constructive/15 text-constructive',
  hold: 'bg-hairline/60 text-muted',
  trim: 'bg-caution/15 text-caution',
  exit: 'bg-defensive/15 text-defensive',
  research_incomplete: 'bg-hairline/40 text-faint',
}

const LEG_COLS: { k: keyof CycleRow; h: string; title: string }[] = [
  { k: 'demand_accel', h: 'dem', title: 'demand acceleration · 20' },
  { k: 'backlog_quality', h: 'bkl', title: 'orders/backlog quality · 15' },
  { k: 'est_revisions', h: 'rev', title: 'estimate revisions · 15' },
  { k: 'margin_cf', h: 'mgn', title: 'margin/cash-flow · 15' },
  { k: 'capacity_util', h: 'cap', title: 'capacity/utilization · 10' },
  { k: 'customer_adoption', h: 'cus', title: 'customer adoption · 10' },
  { k: 'capital_recovery', h: 'fin', title: 'capital recovery · 10' },
  { k: 'valuation_duration', h: 'val', title: 'valuation vs duration · 5' },
]

function legTone(v?: number | null) {
  if (v == null) return 'text-faint/50'
  return v >= 70 ? 'text-aggressive' : v >= 45 ? 'text-ink'
    : v >= 25 ? 'text-caution' : 'text-defensive'
}

function Movement({ m }: { m?: string | null }) {
  if (!m || m === 'new') return <span className="text-faint">—</span>
  if (m === 'pulled_forward')
    return <span className="text-defensive">▼ pulled fwd</span>
  if (m === 'pushed_out')
    return <span className="text-aggressive">▲ pushed out</span>
  return <span className="text-faint">= unchanged</span>
}

function PeakDots({ r }: { r: CycleRow }) {
  const dot = (b?: boolean | null, t?: string) => (
    <span
      title={t}
      className={`inline-block h-1.5 w-1.5 rounded-full ${
        b == null ? 'bg-hairline' : b ? 'bg-defensive' : 'bg-constructive'}`}
    />
  )
  return (
    <span className="inline-flex items-center gap-1">
      {dot(r.order_peak, 'peak 1 — orders')}
      {dot(r.estimate_peak, 'peak 2 — estimates')}
      {dot(r.revenue_peak, 'peak 3 — revenue')}
    </span>
  )
}

function History({ sym }: { sym: string }) {
  const [rows, setRows] = useState<CycleHistoryRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (rows == null && err == null) {
    fetch(`/api/cycle-history/${encodeURIComponent(sym)}`)
      .then(r => r.json())
      .then(d => setRows(d.rows ?? []))
      .catch(e => setErr(String(e)))
  }
  if (err) return <div className="py-2 text-xs text-defensive">{err}</div>
  if (rows == null)
    return <div className="py-2 text-xs text-faint">loading…</div>
  if (!rows.length)
    return <div className="py-2 text-xs text-faint">no prior quarters</div>
  return (
    <table className="w-full text-[11px]">
      <thead>
        <tr className="text-left text-faint">
          <th className="py-1 pr-3 font-normal">quarter</th>
          <th className="py-1 pr-3 font-normal">decision</th>
          <th className="py-1 pr-3 font-normal text-right">score</th>
          <th className="py-1 pr-3 font-normal text-right">peak risk</th>
          <th className="py-1 pr-3 font-normal">peak window</th>
          <th className="py-1 pr-3 font-normal">movement</th>
          <th className="py-1 font-normal">peaks</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((h, i) => (
          <tr key={i} className="border-t border-hairline/50">
            <td className="py-1.5 pr-3 font-mono text-ink">
              {h.quarter_label}
            </td>
            <td className="py-1.5 pr-3">
              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase ${DEC_TONE[h.decision ?? ''] ?? 'bg-hairline/40 text-faint'}`}>
                {(h.decision ?? '—').replace(/_/g, ' ')}
              </span>
            </td>
            <td className="py-1.5 pr-3 text-right font-mono">
              {h.composite ?? '—'}
            </td>
            <td className="py-1.5 pr-3 text-right font-mono">
              {h.rev_peak_risk ?? '—'}
            </td>
            <td className="py-1.5 pr-3 font-mono">
              {h.demand_peak_lo
                ? `${h.demand_peak_lo}–${h.demand_peak_hi ?? h.demand_peak_lo}`
                : '—'}
            </td>
            <td className="py-1.5 pr-3"><Movement m={h.peak_movement} /></td>
            <td className="py-1.5"><PeakDots r={h as CycleRow} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function CycleTable({ rows }: { rows: CycleRow[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-hairline text-left text-[10px] uppercase tracking-wider text-faint">
            <th className="py-2 pr-2 font-medium" />
            <th className="py-2 pr-3 font-medium">symbol</th>
            <th className="py-2 pr-3 font-medium">cohort</th>
            <th className="py-2 pr-3 font-medium">decision</th>
            <th className="py-2 pr-3 font-medium text-right">score</th>
            <th className="py-2 pr-3 font-medium text-right"
                title="share of the 100-pt spec answered">cov</th>
            {LEG_COLS.map(l => (
              <th key={l.h} title={l.title}
                  className="py-2 pr-2 font-medium text-right">
                {l.h}
              </th>
            ))}
            <th className="py-2 px-2 font-medium text-right"
                title="revenue-peak risk 0-100">pkr</th>
            <th className="py-2 px-2 font-medium text-center"
                title="peaks: orders · estimates · revenue">peaks</th>
            <th className="py-2 pl-2 font-medium">demand peak</th>
            <th className="py-2 pl-2 font-medium">move</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const expanded = open === r.symbol
            const seeded = r.peak_source === 'cohort_seed'
            return [
              <tr key={r.symbol}
                  onClick={() => setOpen(expanded ? null : r.symbol)}
                  className="cursor-pointer border-b border-hairline/60 hover:bg-hairline/20">
                <td className="py-2 pr-2 text-faint">
                  {expanded ? '▾' : '▸'}
                </td>
                <td className="py-2 pr-3">
                  <Link href={`/stock?sym=${r.symbol}`}
                        onClick={e => e.stopPropagation()}
                        className="font-semibold text-ink hover:text-accent">
                    {r.symbol}
                  </Link>
                </td>
                <td className="py-2 pr-3 text-faint">
                  {(r.cohort ?? '—').replace(/_/g, ' ')}
                </td>
                <td className="py-2 pr-3">
                  <span className={`rounded-full px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider ${DEC_TONE[r.decision ?? ''] ?? 'bg-hairline/40 text-faint'}`}>
                    {(r.decision ?? '—').replace(/_/g, ' ')}
                  </span>
                  {r.valuation_blocked && (
                    <span title="valuation blocked"
                          className="ml-1 text-caution">⛔</span>
                  )}
                </td>
                <td className={`py-2 pr-3 text-right font-mono font-semibold ${legTone(r.composite)}`}>
                  {r.composite ?? '—'}
                </td>
                <td className="py-2 pr-3 text-right font-mono text-faint">
                  {r.coverage_pct != null
                    ? `${Math.round(r.coverage_pct * 100)}%` : '—'}
                </td>
                {LEG_COLS.map(l => (
                  <td key={l.h}
                      className={`py-2 pr-2 text-right font-mono ${legTone(r[l.k] as number | null)}`}>
                    {r[l.k] == null
                      ? <span className="text-faint/40">·</span>
                      : r[l.k]}
                  </td>
                ))}
                <td className={`py-2 px-2 text-right font-mono ${
                  (r.rev_peak_risk ?? 0) >= 70 ? 'text-defensive'
                  : (r.rev_peak_risk ?? 0) >= 40 ? 'text-caution'
                  : 'text-ink'}`}>
                  {r.rev_peak_risk ?? '—'}
                </td>
                <td className="py-2 px-2 text-center"><PeakDots r={r} /></td>
                <td className="py-2 pl-2 font-mono text-ink">
                  {r.demand_peak_lo
                    ? `${r.demand_peak_lo}–${r.demand_peak_hi ?? r.demand_peak_lo}`
                    : '—'}
                  {r.demand_peak_lo && seeded && (
                    <span className="text-faint" title="cohort seed — unverified">*</span>
                  )}
                  {r.quarters_to_peak != null && (
                    <span className="ml-1 text-faint">
                      {r.quarters_to_peak}q
                    </span>
                  )}
                </td>
                <td className="py-2 pl-2"><Movement m={r.peak_movement} /></td>
              </tr>,
              expanded && (
                <tr key={`${r.symbol}-h`}>
                  <td colSpan={17}
                      className="border-b border-hairline bg-card/60 px-8 py-3">
                    <History sym={r.symbol} />
                  </td>
                </tr>
              ),
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}
