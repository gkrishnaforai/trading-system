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

const LEG_NAME: Record<string, string> = {
  demand_accel: 'Demand acceleration',
  backlog_quality: 'Orders & backlog',
  est_revisions: 'Estimate revisions',
  margin_cf: 'Margins & cash flow',
  capacity_util: 'Capacity & utilization',
  customer_adoption: 'Customer adoption',
  capital_recovery: 'Capital & financing',
  valuation_duration: 'Valuation vs runway',
}

const FLAG_TXT: Record<string, string> = {
  insufficient_evidence:
    'evidence is thin — this verdict is provisional',
  order_peak_warning:
    'orders may have peaked — momentum flag, verify before adding',
  peak_window_unsourced:
    'peak window is a cohort estimate, not verified evidence',
  competition_unverified:
    'no competitive-threat evidence journaled yet',
  competitive_risk_deteriorating:
    'competitive resilience is deteriorating quarter over quarter',
  insourcing_beneficiary:
    'customer insourcing may expand this company\u2019s opportunity',
}

const STAGE_TONE: Record<string, string> = {
  announced: 'bg-hairline/60 text-faint',
  prototype: 'bg-hairline/60 text-muted',
  design_win: 'bg-caution/15 text-caution',
  qualification: 'bg-caution/25 text-caution',
  production: 'bg-defensive/15 text-defensive',
  scaled: 'bg-defensive/25 text-defensive',
}

function ThreatList({ r }: { r: CycleRow }) {
  const threats = r.top_threats ?? []
  const opp = r.opportunity_credit
  if (!threats.length && (r.crs == null) && !opp) return null
  return (
    <div className="mt-3 border-t border-hairline/50 pt-2">
      <div className="mb-1.5 flex items-baseline gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">
          Competitive
        </span>
        {r.crs != null && (
          <span className="text-[11px] font-mono text-ink">
            resilience {r.crs}
            {r.risk_trend === 'deteriorating' && (
              <span className="text-defensive"> ▼</span>)}
            {r.risk_trend === 'improving' && (
              <span className="text-aggressive"> ▲</span>)}
          </span>
        )}
        {r.displacement_confirmed && (
          <span className="rounded-full bg-defensive/15 px-2 py-0.5 text-[9px] font-semibold uppercase text-defensive">
            displacement confirmed
          </span>
        )}
        {opp != null && opp > 0 && (
          <span className="text-[10px] text-constructive">
            +{opp} opportunity credit
          </span>
        )}
      </div>
      {threats.length > 0 ? (
        <ul className="space-y-1">
          {threats.map((t, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-[11px]">
              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${STAGE_TONE[t.stage ?? ''] ?? 'bg-hairline/40 text-faint'}`}>
                {(t.stage ?? '?').replace(/_/g, ' ')}
              </span>
              <span className="font-medium text-ink">{t.competitor}</span>
              <span className="text-faint">{t.segment}</span>
              {t.share?.[0] != null && (
                <span className="font-mono text-caution">
                  {Math.round((t.share[0] ?? 0) * 100)}–
                  {Math.round((t.share[1] ?? t.share[0] ?? 0) * 100)}% at risk
                </span>
              )}
              <span className="text-faint/70">
                {t.claim}
                {t.source_date && ` · ${t.source_date}`}
                {t.source === 'framework_doc' && ' · seed'}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-[11px] text-faint">
          no approved threat claims journaled
        </div>
      )}
    </div>
  )
}

/** The "why" — translate the journaled decision into plain English:
 * the fired rule's note, the strongest and weakest evidence legs,
 * and the honest caveats. Nothing here is generated — every line
 * restates a journaled number or note. */
const AGENTIC_TIER: Record<string, string> = {
  core_infrastructure: 'bg-constructive/15 text-constructive',
  emerging: 'bg-caution/15 text-caution',
  watch: 'bg-hairline/60 text-muted',
  candidate: 'bg-hairline/40 text-faint',
}

function AgenticBlock({ r }: { r: CycleRow }) {
  if (r.ais == null && !(r.sublayers ?? []).length) return null
  return (
    <div className="mt-3 border-t border-hairline/50 pt-2">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">
          Agentic infra
        </span>
        {r.ais != null && (
          <span className="text-[11px] font-mono text-ink">
            ais {r.ais}
          </span>
        )}
        {r.agentic_tier && (
          <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase ${AGENTIC_TIER[r.agentic_tier] ?? 'bg-hairline/40 text-faint'}`}>
            {r.agentic_tier.replace(/_/g, ' ')}
          </span>
        )}
        {r.monetization && (
          <span className="text-[10px] text-faint">
            {r.monetization}-priced
          </span>
        )}
        {(r.sublayers ?? []).map(s => (
          <span key={s}
                className="rounded-full bg-hairline/50 px-1.5 py-0.5 text-[9px] text-muted">
            {s.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
    </div>
  )
}

function WhyPanel({ r }: { r: CycleRow }) {
  const comps = Object.entries(r.components ?? {})
  const scored = comps.filter(([, c]) => c.score != null)
    .sort((a, b) => (b[1].score ?? 0) - (a[1].score ?? 0))
  const unknown = comps.filter(([, c]) => c.unknown)
  const top = scored.slice(0, 3)
  const weak = scored.filter(([, c]) => (c.score ?? 100) < 35)
  const dd = r.decision_detail
  return (
    <div className="space-y-2 text-[11.5px]">
      {dd?.note && (
        <div className="text-ink">
          <span className="text-faint">Why: </span>
          {dd.note}
          {r.rev_peak_risk != null && (
            <span className="text-faint">
              {' '}· peak risk {r.rev_peak_risk}/100
            </span>
          )}
        </div>
      )}
      {top.length > 0 && (
        <div>
          <span className="text-faint">Strongest evidence — </span>
          <span className="text-ink">
            {top.map(([k, c]) =>
              `${LEG_NAME[k] ?? k} ${c.score}` +
              (c.note ? ` (${c.note})` : '')).join(' · ')}
          </span>
        </div>
      )}
      {weak.length > 0 && (
        <div className="text-caution">
          <span className="text-faint">Watch — </span>
          {weak.map(([k, c]) =>
            `${LEG_NAME[k] ?? k} ${c.score}` +
            (c.note ? ` (${c.note})` : '')).join(' · ')}
        </div>
      )}
      {unknown.length > 0 && (
        <div className="text-faint">
          No evidence yet for:{' '}
          {unknown.map(([k]) => LEG_NAME[k] ?? k).join(', ')}
          {' '}— excluded from the score, not counted as zero.
        </div>
      )}
      {(r.flags ?? []).length > 0 && (
        <ul className="text-faint">
          {(r.flags ?? []).map(f => (
            <li key={f}>· {FLAG_TXT[f] ?? f.replace(/_/g, ' ')}</li>
          ))}
        </ul>
      )}
      {(dd?.missing ?? []).length > 0 && (
        <div className="text-faint/70">
          unverifiable inputs: {(dd?.missing ?? []).slice(0, 6).join(', ')}
        </div>
      )}
    </div>
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
            <th className="py-2 px-2 font-medium text-right"
                title="competitive resilience 0-100 — click row for threats">crs</th>
            <th className="py-2 px-2 font-medium text-right"
                title="agentic infrastructure score 0-100 — software picks-and-shovels for agents; click row for sublayers">ais</th>
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
                  <span title={r.decision_detail?.note ?? undefined}
                        className={`rounded-full px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider ${DEC_TONE[r.decision ?? ''] ?? 'bg-hairline/40 text-faint'}`}>
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
                {LEG_COLS.map(l => {
                  const v = r[l.k] as number | null | undefined
                  return (
                    <td key={l.h}
                        className={`py-2 pr-2 text-right font-mono ${legTone(v)}`}>
                      {v == null
                        ? <span className="text-faint/40">·</span>
                        : v}
                    </td>
                  )
                })}
                <td className={`py-2 px-2 text-right font-mono ${
                  (r.rev_peak_risk ?? 0) >= 70 ? 'text-defensive'
                  : (r.rev_peak_risk ?? 0) >= 40 ? 'text-caution'
                  : 'text-ink'}`}>
                  {r.rev_peak_risk ?? '—'}
                </td>
                <td className={`py-2 px-2 text-right font-mono ${
                  r.displacement_confirmed ? 'text-defensive'
                  : legTone(r.crs)}`}
                    title={r.displacement_confirmed
                      ? 'production-stage displacement confirmed'
                      : r.risk_trend === 'deteriorating'
                      ? 'competitive risk deteriorating' : undefined}>
                  {r.crs ?? <span className="text-faint/40">·</span>}
                  {r.displacement_confirmed && ' ⚠'}
                </td>
                <td className={`py-2 px-2 text-right font-mono ${legTone(r.ais)}`}
                    title={r.agentic_tier
                      ? `${r.agentic_tier.replace(/_/g, ' ')}${
                          (r.sublayers ?? []).length
                            ? ' — ' + (r.sublayers ?? [])
                                .join(', ').replace(/_/g, ' ')
                            : ''}`
                      : undefined}>
                  {r.ais ?? <span className="text-faint/40">·</span>}
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
                  <td colSpan={18}
                      className="border-b border-hairline bg-card/60 px-8 py-3">
                    <div className="mb-3">
                      <WhyPanel r={r} />
                      <AgenticBlock r={r} />
                      <ThreatList r={r} />
                    </div>
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
