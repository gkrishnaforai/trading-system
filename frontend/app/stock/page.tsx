import Link from 'next/link'
import { api } from '@/lib/api'
import { Suspense, type ReactNode } from 'react'
import { Chip, Gate, Kv, Section, Stat, fmtShort } from '@/components/regime'
import { FundPanel, TapePanel } from '@/components/panels'
import { TheCall } from '@/components/thecall'
import { WatchToggle } from '@/components/watchlist'
import { ThesisFlag } from '@/components/thesis-flag'
import { ThesisReport } from '@/components/thesis-report'
import { SignalStrip, toneOf } from '@/components/signal-strip'
import FvRecompute from '@/components/fv-recompute'

function num(v: unknown) {
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

function money(v: unknown, dec = 2) {
  const n = Number(v)
  return Number.isFinite(n) ? `$${n.toFixed(dec)}` : '—'
}

function pct(v: unknown, dec = 1) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(dec)}%`
}

function pctTone(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 0 ? 'text-aggressive' : 'text-defensive'
}

function daysOld(d?: string | null) {
  if (!d) return null
  const t = Date.parse(d)
  if (!Number.isFinite(t)) return null
  return Math.max(0, Math.round((Date.now() - t) / 86400000))
}

function Fresh({
  date, warnDays = 90, prefix,
}: { date?: string | null; warnDays?: number; prefix?: string }) {
  const age = daysOld(date)
  if (age == null) return null
  const stale = age > warnDays
  return (
    <span
      className={`font-mono text-[11px] ${stale ? 'text-caution' : 'text-faint'}`}
    >
      {stale && '⚠ '}{prefix ?? ''}{String(date).slice(0, 10)} · {age}d old
    </span>
  )
}

/** One-sentence read — tape × fundamentals × valuation × trust, in
    words not numbers. Sits under the hero so the page answers "so
    what" before any detail. */
function readLine(card: Record<string, unknown>): string {
  const t = obj(card.technical)?.state
  const f = obj(card.fundamental)?.state
  const dcf = obj(card.data_confidence)?.grade
  const fv = obj(card.fv)
  const fvWord =
    fv?.valuation_status === 'needs_validation' ? 'fair value unverified'
      : card.fv_upside_pct != null
        ? `fair value ${pct(card.fv_upside_pct)} vs spot`
        : 'no fair value yet'
  const parts = [
    t ? `${String(t)} tape` : null,
    f ? `${String(f)} fundamentals` : null,
    fvWord,
    dcf ? `data confidence ${String(dcf)}` : null,
  ].filter(Boolean)
  return parts.join(' · ')
}

/** 60-day close sparkline — pure SVG, zero client JS. */
function Sparkline({ closes, spot, asOf }: {
  closes: number[]; spot?: number | null; asOf?: string | null
}) {
  if (!closes || closes.length < 5) return null
  const w = 720, h = 56, pad = 4
  const lo = Math.min(...closes), hi = Math.max(...closes)
  const span = hi - lo || 1
  const pts = closes
    .map((c, i) =>
      `${(pad + (i / (closes.length - 1)) * (w - 2 * pad)).toFixed(1)},` +
      `${(h - pad - ((c - lo) / span) * (h - 2 * pad)).toFixed(1)}`)
    .join(' ')
  const last = closes[closes.length - 1]
  const lastY = h - pad - ((last - lo) / span) * (h - 2 * pad)
  const chg = closes.length > 1
    ? ((last / closes[0]) - 1) * 100 : 0
  return (
    <div className="pt-3">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-14 w-full"
        preserveAspectRatio="none" role="img"
        aria-label={`60-day close range ${lo.toFixed(2)} to ${hi.toFixed(2)}`}>
        <polyline points={pts} fill="none" stroke="#78716C"
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <circle cx={w - pad} cy={lastY} r="3" fill="#EA580C" />
      </svg>
      <div className="flex justify-between font-mono text-[10px] text-faint">
        <span>60d low {money(lo)}</span>
        <span className={chg >= 0 ? 'text-aggressive' : 'text-defensive'}>
          {chg >= 0 ? '+' : ''}{chg.toFixed(0)}% · {money(last)}
          {asOf != null && (
            <span className={`text-faint ${asOf < new Date(Date.now() - 4 * 864e5).toISOString().slice(0, 10) ? ' text-caution' : ''}`}>
              {' '}· {asOf}
            </span>
          )}
        </span>
        <span>60d high {money(hi)}</span>
      </div>
    </div>
  )
}

/** Earnings event with provenance — date, session, source, verified
    age, and the staleness invariant surfaced as a warning. */
function EarningsBlock({ e }: { e: Record<string, unknown> | null }) {
  if (!e || (!e.date && !e.last_print_date)) return null
  const days = typeof e.days === 'number' ? e.days : null
  const stale = Boolean(e.stale)
  const soon = days != null && days >= 0 && days <= 14
  const issues = Array.isArray(e.issues) ? e.issues : []
  return (
    <span
      className={`text-xs ${stale || soon ? 'text-caution' : 'text-muted'}`}
      title={issues.map(String).join(' · ')}
    >
      {(stale || soon) && '⚠ '}
      {e.date ? (
        <>
          earnings {String(e.date)}
          {days != null && days >= 0 && ` · in ${days}d`}
          {e.session != null && ` ${String(e.session)}`}
        </>
      ) : 'no earnings date'}
      {e.source != null && (
        <span className="text-faint"> · {String(e.source)}</span>
      )}
      {e.verified_age_days != null && (
        <span className="text-faint">
          {' '}· verified {Number(e.verified_age_days)}d ago
        </span>
      )}
      {stale && issues.length > 0 && (
        <span className="text-caution"> — {String(issues[0])}</span>
      )}
    </span>
  )
}

/** Sector-relative leadership — 'who leads the group': RS rank, the
    day-level defense/offense pattern vs the group benchmark, and the
    estimate-stability confirmation. Selection vocabulary, never an
    entry trigger. */
function Leadership({ l }: { l: Record<string, unknown> | null }) {
  if (!l) return null
  const pct = num(l.rs_pct)
  if (pct == null) return null
  const bench = String(l.bench || 'SPY')
  const q = String(l.quality || '')
  const dc = num(l.down_cap), dn = num(l.down_n)
  const uc = num(l.up_cap), un = num(l.up_n), rx = num(l.rebound_x)
  const rev = num(l.est_rev)
  const parts: string[] = [`RS ${Math.round(pct)}th pct vs ${bench}`]
  if (l.rs_nh === true) parts.push('RS line new high')
  if (dc != null && dn != null && dn > 0)
    parts.push(`defends ${Math.round(dc * dn)}/${dn} red days`)
  if (uc != null && un != null && un > 0)
    parts.push(`outperforms ${Math.round(uc * un)}/${un} green days`
      + (rx != null ? ` · ${rx >= 0 ? '+' : ''}${(rx * 100).toFixed(1)}%` : ''))
  if (rev != null)
    parts.push(`est rev ${rev > 0 ? '+' : ''}${(rev * 100).toFixed(0)}%`)
  const tone = q === 'resilient' ? 'text-aggressive'
    : q === 'fragile' ? 'text-defensive' : 'text-muted'
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 pt-1 text-xs">
      <span className={`font-medium ${tone}`}>
        {q || 'leadership'}
      </span>
      <span className="text-muted">{parts.join(' · ')}</span>
    </div>
  )
}

/** Rolled-up data trust — one chip answering 'can I trust this page'. */
function ConfChip({ d }: { d: Record<string, unknown> | null }) {
  if (!d?.grade) return null
  const g = String(d.grade)
  const issues = Array.isArray(d.issues) ? d.issues : []
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${g === 'high' ? 'border-aggressive/40 text-aggressive'
        : g === 'medium' ? 'border-caution/40 text-caution'
          : 'border-defensive/40 text-defensive'
        }`}
      title={issues.map(String).join(' · ')}
    >
      data {g}{issues.length > 0 ? ` (${issues.length})` : ''}
    </span>
  )
}

/** FV scenario range — bear…base…bull band with expected + spot
    markers. A picture of the distribution, not just three numbers. */
function FvRange({ scen, expected, spot }: {
  scen: Record<string, unknown> | null
  expected?: unknown
  spot?: number | null
}) {
  const bear = Number(scen?.bear), base = Number(scen?.base),
    bull = Number(scen?.bull), exp = Number(expected)
  const vals = [bear, base, bull, exp, spot].filter(
    (v): v is number => Number.isFinite(v))
  if (vals.length < 3 || !(bull > bear)) return null
  const lo = Math.min(...vals) * 0.97, hi = Math.max(...vals) * 1.03
  const span = hi - lo
  const x = (v: number) => ((v - lo) / span) * 100
  return (
    <div className="pt-4">
      <div className="relative h-2 rounded-full bg-elevated">
        {Number.isFinite(bear) && Number.isFinite(bull) && (
          <div
            className="absolute inset-y-0 rounded-full bg-accent/20"
            style={{ left: `${x(bear)}%`, width: `${x(bull) - x(bear)}%` }}
          />
        )}
        {Number.isFinite(base) && (
          <span className="absolute -top-1 h-4 w-[2px] bg-faint"
            style={{ left: `${x(base)}%` }} title={`base ${money(base)}`} />
        )}
        {Number.isFinite(exp) && (
          <span className="absolute -top-1.5 h-5 w-[3px] rounded bg-ink"
            style={{ left: `${x(exp)}%` }} title={`expected ${money(exp)}`} />
        )}
        {Number.isFinite(Number(spot)) && (
          <span
            className="absolute -top-1.5 h-5 w-[3px] rounded bg-accent"
            style={{ left: `${x(Number(spot))}%` }}
            title={`spot ${money(spot)}`} />
        )}
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[10px] text-faint">
        <span>bear {money(bear)}</span>
        <span>base {money(base)} · expected {money(exp)} ·
          {' '}<span className="text-accent">spot {money(spot)}</span></span>
        <span>bull {money(bull)}</span>
      </div>
    </div>
  )
}

/** Small labeled stat — label above value, the design-system cell. */
function MiniL({ label, children }: {
  label: string; children: ReactNode
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-faint">
        {label}
      </div>
      <div className="pt-0.5 font-mono text-xs text-ink">{children}</div>
    </div>
  )
}

/** Drawdown attribution — the selloff engine's per-symbol read:
    what KIND of fall this is (macro panic vs fundamental repricing),
    the opportunity score, the hard gates, and the staged entry plan.
    Lives next to 'why is it moving' — same question at drawdown
    depth. */
function SelloffPanel({ s }: { s: Record<string, unknown> }) {
  const cls = String(s.classification ?? '—').replace(/_/g, ' ')
  const dec = String(s.decision ?? '—')
  const gates = Array.isArray(s.gates) ? s.gates.map(String) : []
  const legs = obj(s.score_legs ?? s.legs)
  const plan = obj(s.entry_plan)
  const stages = Array.isArray(plan?.stages)
    ? (plan!.stages as Record<string, unknown>[])
    : []
  const tape = obj(s.tape)
  const dd = Number(s.dd_60d ?? tape?.dd_60d)
  const clsTone =
    /impairment|repricing|weakness/.test(cls)
      ? 'text-defensive'
      : /panic|contagion|unwind/.test(cls)
        ? 'text-aggressive'
        : 'text-muted'
  const decTone =
    dec === 'priority' || dec === 'starter'
      ? 'text-aggressive'
      : dec === 'reject'
        ? 'text-defensive'
        : dec === 'watch'
          ? 'text-caution'
          : 'text-muted'
  return (
    <div className="pt-3 border-t border-hairline/60 mt-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
          drawdown attribution
        </span>
        <span className="font-mono text-[10px] text-faint">
          {s.stale === true ? `last scan · ${String(s.as_of ?? '')}` : 'live'}
        </span>
      </div>
      <div className="pt-2 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2">
        <MiniL label="classification">
          <span className={clsTone}>{cls}</span>
        </MiniL>
        <MiniL label="score">
          {s.score != null ? `${String(s.score)}/100` : '—'}
        </MiniL>
        <MiniL label="decision">
          <span className={decTone}>{dec}</span>
        </MiniL>
        <MiniL label="60d drawdown">
          {Number.isFinite(dd)
            ? `${(dd * 100).toFixed(1)}%`
            : '—'}
        </MiniL>
      </div>
      {typeof s.action === 'string' && s.action && (
        <p className="pt-2 text-xs text-muted leading-relaxed">
          {s.action}
        </p>
      )}
      {gates.length > 0 && (
        <div className="pt-2">
          <div className="text-[10px] uppercase tracking-wider text-faint">
            hard gates
          </div>
          <ul className="pt-1 space-y-0.5 text-xs text-defensive">
            {gates.slice(0, 4).map((g, i) => (
              <li key={i}>· {g}</li>
            ))}
          </ul>
        </div>
      )}
      {legs && (
        <div className="pt-2 font-mono text-[11px] text-faint">
          {Object.entries(legs)
            .map(([k, v]) => `${k.replace(/_/g, ' ')} ${String(v)}`)
            .join(' · ')}
        </div>
      )}
      {stages.length > 0 && (
        <div className="pt-2">
          <div className="text-[10px] uppercase tracking-wider text-faint">
            staged entry
          </div>
          <ul className="pt-1 space-y-0.5 text-xs text-muted">
            {stages.map((st, i) => (
              <li key={i}>
                · {String(st.pct ?? '—')}% — {String(st.trigger ?? '')}
              </li>
            ))}
            {plan?.invalidation != null && (
              <li className="text-defensive">
                · invalidation {String(plan.invalidation)} —{' '}
                {String(plan.invalidation_note ?? '')}
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

/** 'Why is it moving' — every diagnosis field, labeled, in a compact
    grid + readable line + event wire. Same info as the raw dump,
    minus the column of whitespace. */
function Diagnosis({ d }: { d: Record<string, unknown> }) {
  const attr = obj(d.attribution)
  const causes = Array.isArray(d.causes) ? d.causes.map(String) : []
  const verdict = d.verdict != null
    ? String(d.verdict).replace(/_/g, ' ') : null
  const fmtR = (v: unknown) => {
    const x = Number(v)
    return Number.isFinite(x)
      ? `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%` : '—'
  }
  const toneR = (v: unknown) => {
    const x = Number(v)
    return !Number.isFinite(x) ? 'text-muted'
      : x < 0 ? 'text-defensive'
        : x > 0 ? 'text-aggressive' : 'text-muted'
  }
  const dirT = d.direction === 'weak' ? 'text-defensive'
    : d.direction === 'strong' ? 'text-aggressive' : 'text-muted'
  const vTone = /earned|accumulat/.test(verdict ?? '')
    ? 'text-aggressive'
    : /hype|unexplained|knife/.test(verdict ?? '')
      ? 'text-caution' : 'text-muted'
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.18em] text-faint">
        why is it moving
      </div>
      {/* the facts — every field labeled, one compact row */}
      <div className="pt-2 grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2">
        <MiniL label="direction">
          <span className={dirT}>{String(d.direction ?? '—')}</span>
        </MiniL>
        <MiniL label="state">{String(d.state ?? '—')}</MiniL>
        <MiniL label="sessions in state">
          {String(d.sessions_in_state ?? '—')}
        </MiniL>
        <MiniL label="verdict">
          <span className={vTone}>{verdict ?? '—'}</span>
        </MiniL>
      </div>
      {/* attribution — labeled, one comparative line */}
      {attr && (
        <div className="pt-2.5">
          <div className="text-[10px] uppercase tracking-wider text-faint">
            attribution
          </div>
          <div className="pt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono text-xs text-muted">
            <span>
              <span className="text-faint">stock </span>
              <span className={toneR(attr.stock_5d)}>
                {fmtR(attr.stock_5d)}
              </span>
              <span className="text-faint"> 5d</span>
            </span>
            <span>
              <span className={toneR(attr.stock_20d)}>
                {fmtR(attr.stock_20d)}
              </span>
              <span className="text-faint"> 20d</span>
            </span>
            <span className="text-faint">vs</span>
            {attr.sector_etf != null && (
              <span>
                <span className="text-faint">
                  {String(attr.sector_etf)}{' '}
                </span>
                <span className={toneR(attr.sector_5d)}>
                  {fmtR(attr.sector_5d)}
                </span>
              </span>
            )}
            <span>
              <span className="text-faint">SPY </span>
              <span className={toneR(attr.spy_5d)}>
                {fmtR(attr.spy_5d)}
              </span>
            </span>
          </div>
        </div>
      )}
      {/* the explanation */}
      {d.line != null && (
        <p className="pt-2 text-xs text-muted leading-relaxed">
          {String(d.line)}
          {d.note != null && (
            <span className="text-faint"> · {String(d.note)}</span>
          )}
        </p>
      )}
      {/* causes — the event wire, dated */}
      <div className="pt-2">
        <div className="text-[10px] uppercase tracking-wider text-faint">
          causes
        </div>
        {causes.length > 0 ? (
          <ul className="pt-0.5 space-y-0.5">
            {causes.slice(0, 5).map((c, i) => {
              const j = c.indexOf(' · ')
              const dt = j > 0 ? c.slice(5, j) : null
              const title = j > 0 ? c.slice(j + 3) : c
              return (
                <li key={i}
                  className="text-[11px] leading-snug text-muted">
                  {dt != null && (
                    <span className="font-mono text-faint">
                      {dt}{' '}
                    </span>
                  )}
                  {title}
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="pt-0.5 text-[11px] text-faint">
            — no events on the wire in the window
          </div>
        )}
      </div>
    </div>
  )
}

function stateTone(s?: unknown) {
  const v = String(s ?? '').toLowerCase()
  if (['ready', 'confirmed', 'accelerating', 'healthy', 'improving', 'strong']
    .some((t) => v.includes(t))) return 'text-aggressive'
  if (['no', 'broken', 'blocked', 'deteriorating', 'broken_down', 'failed',
    'chase_block'].some((t) => v.includes(t))) return 'text-defensive'
  if (['close', 'watch', 'caution', 'stalling', 'mixed']
    .some((t) => v.includes(t))) return 'text-caution'
  return 'text-muted'
}

function obj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

export default function StockPage({
  searchParams,
}: {
  searchParams: { sym?: string | string[] }
}) {
  const raw = searchParams.sym
  const sym = (Array.isArray(raw) ? raw[0] : raw ?? '')
    .toUpperCase().trim()

  if (!sym) {
    return (
      <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
        <p className="text-sm text-muted">
          No symbol — open a stock from the{' '}
          <Link href="/board" className="text-accent underline">board</Link>.
        </p>
      </main>
    )
  }

  // stream: the card fetch gates first paint; squeeze + alerts are
  // independent fetches inside their own Suspense boundaries — they
  // pop in when ready instead of blocking the whole page
  return (
    <Suspense fallback={<StockSkeleton sym={sym} />}>
      <StockCore sym={sym} />
    </Suspense>
  )
}

function StockSkeleton({ sym }: { sym: string }) {
  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <div className="pt-6 pb-2 text-xs text-faint">← board</div>
      <header className="pb-8 animate-pulse">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-semibold text-display text-ink">{sym}</h1>
          <div className="h-8 w-24 rounded bg-elevated" />
        </div>
        <div className="mt-3 h-3 w-2/3 rounded bg-elevated" />
        <div className="mt-6 h-24 rounded-xl bg-elevated" />
      </header>
    </main>
  )
}

async function StockCore({ sym }: { sym: string }) {
  const card = await api.stockHealth(sym)
  if (!card) {
    return (
      <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
        <h1 className="font-semibold text-2xl">{sym}</h1>
        <p className="pt-3 text-sm text-muted">
          No data — symbol isn&apos;t on the book, or the worker is
          unreachable.
        </p>
      </main>
    )
  }

  const verdict = obj(card.verdict)
  const fv = obj(card.fv)
  const lastPrint = obj(card.last_print)
  // the quarterly-analysis verdict on the last realized print —
  // earnings_watch verdict when journaled, else derived from the
  // surprise (one-time-adjusted when the scan annotated the row)
  const lpVerdict = (() => {
    if (lastPrint?.verdict) return String(lastPrint.verdict)
    const s = Number(lastPrint?.surprise_percentage)
    if (!lastPrint || Number.isNaN(s)) return null
    if (s >= 5) return 'beat'
    if (s <= -5)
      return lastPrint.adjusted_eps_actual != null
        ? 'miss — one-time charges'
        : 'miss'
    return 'in-line'
  })()
  const lpTone =
    lpVerdict == null ? 'text-muted'
      : /improv|beat/.test(lpVerdict) ? 'text-aggressive'
        : /deterior|miss/.test(lpVerdict) && !/one-time/.test(lpVerdict)
          ? 'text-defensive'
          : 'text-caution'
  const fvScen = obj(fv?.scenarios)
  const fvAnalyst = obj(fv?.analyst)
  const fvMethods = Array.isArray(fv?.methods) ? (fv!.methods as Record<string, unknown>[]) : []
  // blend-level implied basis — the explain strings already carry
  // "fwd EPS 11.76 × 42.8x"; pull the EPS leg so the scenario header
  // can state the blended implied multiple
  const fvEpsBasis = (() => {
    for (const m of fvMethods) {
      const ex = obj(m.explain)
      const s = String(ex?.base ?? ex?.bear ?? Object.values(ex ?? {})[0] ?? '')
      const mm = /EPS ([\d.]+)/.exec(s)
      if (mm) return { eps: Number(mm[1]), basis: s.startsWith('fwd') ? 'fwd EPS' : 'EPS' }
    }
    return null
  })()
  const fundamental = obj(card.fundamental)
  const technical = obj(card.technical)
  const sectorFlow = obj(card.sector_flow)
  const capex = obj(card.capex)
  const sec = obj(card.sec)
  const review = obj(card.review)
  const readiness = obj(card.readiness)
  const thesis = obj(card.thesis) as import('@/components/thesis-flag').Thesis | null
  const diagnosis = card.diagnosis
  const selloff = obj(card.selloff)
  const tailwinds = Array.isArray(card.tailwinds) ? card.tailwinds : []
  const themes = Array.isArray(card.themes) ? card.themes : []
  const upside = card.fv_upside_pct
  const earnings = obj(card.earnings)
  const leadership = obj(card.leadership)
  const dataConf = obj(card.data_confidence)
  const multiples = obj(card.multiples)
  const spark = Array.isArray(card.spark)
    ? (card.spark as unknown[]).map(Number)
      .filter((v): v is number => Number.isFinite(v))
    : []
  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <div className="pt-6 pb-2 text-xs">
        <Link href="/board" className="text-faint hover:text-accent">
          ← board
        </Link>
      </div>

      {/* hero */}
      <header className="pb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-semibold text-display text-ink">
            {sym}
            <span className="ml-3 align-middle"><WatchToggle sym={sym} /></span>
          </h1>
          <div className="text-right">
            <div className="font-mono text-2xl text-ink">
              {money(card.spot)}
            </div>
            {upside != null && (
              <div className={`font-mono text-sm ${pctTone(upside)}`}>
                {pct(upside)} vs fair value
              </div>
            )}
          </div>
        </div>
        <div className="pt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted">
          {card.name != null && <span>{String(card.name)}</span>}
          {card.sector != null && (
            <span className="text-faint">· {String(card.sector)}</span>
          )}
          {card.market_cap != null && (
            <span className="font-mono text-xs text-faint">
              ${(Number(card.market_cap) / 1e9).toFixed(1)}B
            </span>
          )}
          {sectorFlow?.flow != null && (
            <span
              className={`text-xs ${String(sectorFlow.flow).includes('out')
                ? 'text-defensive'
                : String(sectorFlow.flow).includes('in')
                  ? 'text-aggressive'
                  : 'text-muted'
                }`}
            >
              {String(sectorFlow.etf)} {String(sectorFlow.flow)}
              {sectorFlow.score != null && ` ${sectorFlow.score}`}
            </span>
          )}
          <ConfChip d={dataConf} />
        </div>
        {/* the read — one line of words, then the canonical earnings
            event (provenance + staleness) instead of a bare countdown */}
        <p className="pt-2 text-sm text-muted">{readLine(card)}</p>
        <div className="pt-1.5"><EarningsBlock e={earnings} /></div>
        <Leadership l={leadership} />
        {spark.length >= 5 && (
          <Sparkline closes={spark} spot={num(card.spot)}
            asOf={card.spark_as_of ? String(card.spark_as_of) : null} />
        )}
        {/* short positioning — covering vs accumulation (streams in) */}
        <Suspense fallback={null}>
          <SqueezeLine sym={sym} />
        </Suspense>

        {/* glanceable flags — one chip per decision dimension */}
        <div className="pt-4">
          <SignalStrip
            fundamental={fundamental?.state as string | null}
            thesis={thesis}
            technical={technical?.state as string | null}
            fvUpside={typeof upside === 'number' ? upside : null}
            reviewVerdict={review?.verdict as string | null}
          />
        </div>
      </header>

      {/* the call */}
      {verdict && (
        <section
          className={`rounded-xl border border-hairline border-l-4 bg-card px-5 py-4 ${{
            ok: 'border-l-aggressive', warn: 'border-l-caution',
            bad: 'border-l-defensive', off: 'border-l-hairline'
          }[
            toneOf(verdict.verdict)]
            }`}
        >
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              The call
            </span>
            {verdict.verdict != null && (
              <span className={`text-sm font-medium ${stateTone(verdict.verdict)}`}>
                {String(verdict.verdict)}
              </span>
            )}
          </div>
          <div className="pt-3">
            <TheCall card={card} />
          </div>
          {Array.isArray(verdict.why) && verdict.why.length > 0 && (
            <ul className="pt-3 space-y-1 text-sm text-muted leading-relaxed">
              {(verdict.why as unknown[]).slice(0, 6).map((w, i) => (
                <li key={i}>· {String(w)}</li>
              ))}
            </ul>
          )}
          {diagnosis != null && (
            <div className="pt-3 border-t border-hairline/60 mt-3">
              {typeof diagnosis === 'object' ? (
                <Diagnosis d={diagnosis as Record<string, unknown>} />
              ) : (
                <span className="text-xs text-muted">
                  {String(diagnosis)}
                </span>
              )}
            </div>
          )}
          {selloff?.candidate === true && (
            <SelloffPanel s={selloff} />
          )}
        </section>
      )}

      {/* AI research — journaled tailwind score + why, streams in */}
      <Suspense fallback={null}>
        <ResearchSection sym={sym} />
      </Suspense>

      {/* readiness lanes */}
      {readiness && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Readiness
          </div>
          <div className="pt-3 flex flex-wrap gap-2">
            {Object.entries(readiness).map(([lane, v]) => {
              const r = obj(v)
              const state = fmtShort(r?.state ?? r?.readiness ?? v)
              return (
                <span
                  key={lane}
                  className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1 text-xs ${stateTone(state)}`}
                >
                  <span className="text-muted">{lane.replace(/_/g, ' ')}</span>
                  {state}
                </span>
              )
            })}
          </div>
        </section>
      )}

      {/* fair value */}
      {fv && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Fair value
            </span>
            <div className="flex gap-3 items-baseline">
              <FvRecompute sym={sym} />
              <Fresh date={fv.as_of ? String(fv.as_of) : null} />
              {fv.fundamentals_as_of != null && (
                <span className="font-mono text-[11px] text-faint">
                  inputs{' '}
                  <Fresh date={String(fv.fundamentals_as_of)} warnDays={120} />
                </span>
              )}
            </div>
          </div>
          {String(fv.valuation_status ?? '') === 'needs_validation' && (
            <div className="mt-3 rounded-lg border border-caution/40 bg-caution/5 px-3 py-2 text-xs text-caution">
              <span className="font-semibold">valuation flagged — directional only, not decision-grade.</span>
              {Array.isArray(fv.valuation_issues) && (
                <span className="text-muted">
                  {' '}·{' '}
                  {(fv.valuation_issues as unknown[]).map((i) =>
                    String(i).startsWith('stale_inputs')
                      ? `stale inputs (${String(i).split(':')[1]})`
                      : String(i).startsWith('outlier_method')
                        ? `outlier method ${String(i).split(':')[1]}`
                        : String(i),
                  ).join(' · ')}
                </span>
              )}
              <span className="text-faint"> — fundamentals &amp; tape stand alone until this clears</span>
            </div>
          )}
          <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-6">
            <Stat label="Spot" value={money(card.spot ?? fv.spot)} />
            <Stat label="Expected FV · prob-weighted" value={money(fv.expected)} />
            {fvScen?.bear != null && (
              <Stat label="Bear" value={money(fvScen.bear)} />
            )}
            {fvScen?.bull != null && (
              <Stat label="Bull" value={money(fvScen.bull)} />
            )}
          </div>
          {fvScen?.base != null && (
            <div className="pt-3 text-xs text-muted font-mono">
              base {money(fvScen.base)}
              <span className="text-faint"> (central scenario)</span>
              {fvEpsBasis &&
                ` ≈ ${fvEpsBasis.basis} ${fvEpsBasis.eps} × ${(Number(fvScen.base) / fvEpsBasis.eps).toFixed(1)}x blended`}
              {fv.regime != null && ` · regime ${String(fv.regime)}`}
              {fv.spot_at_run != null &&
                Number(fv.spot_at_run) !== Number(card.spot) &&
                ` · spot at run ${money(fv.spot_at_run)}`}
            </div>
          )}
          <FvRange scen={fvScen} expected={fv.expected}
            spot={num(card.spot ?? fv.spot)} />
          {/* multiples — the P/E context for the blend: trailing off
              journaled actuals, forward off consensus */}
          {multiples && (multiples.pe_ttm != null ||
            multiples.fwd_pe != null) && (
              <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-xs text-muted">
                <span className="text-[10px] uppercase tracking-wider text-faint font-sans">
                  multiples
                </span>
                <span>
                  <span className="text-faint">P/E ttm </span>
                  {multiples.pe_ttm != null
                    ? `${Number(multiples.pe_ttm).toFixed(0)}×`
                    : '—'}
                </span>
                <span>
                  <span className="text-faint">fwd </span>
                  {multiples.fwd_pe != null
                    ? `${Number(multiples.fwd_pe).toFixed(0)}×`
                    : '—'}
                  {multiples.fwd_eps != null && (
                    <span className="text-faint">
                      {' '}(est {money(multiples.fwd_eps)})
                    </span>
                  )}
                </span>
              </div>
            )}
          {Array.isArray(fv.flags) && fv.flags.length > 0 && (
            <div className="pt-3 flex flex-wrap gap-2">
              {(fv.flags as unknown[]).map((f, i) => (
                <Chip key={i} label={String(f)} tone="warn" />
              ))}
            </div>
          )}
          {fvAnalyst && (
            <p className="pt-3 text-xs text-faint">
              street: {money(fvAnalyst.consensus_price_target)}
              {fvAnalyst.price_target_low != null &&
                ` (${money(fvAnalyst.price_target_low)}–${money(fvAnalyst.price_target_high)})`}
              {fvAnalyst.analyst_count != null &&
                ` · ${String(fvAnalyst.analyst_count)} analysts`}
              {' — context, not the blend'}
            </p>
          )}
        </section>
      )}

      {/* fundamentals + tape — fundamentals carries ~3x the data,
          so it takes the wide column */}
      <section className="mt-2 grid lg:grid-cols-5 gap-2">
        <div className="rounded-xl border border-hairline bg-card px-5 py-4 lg:col-span-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Fundamentals
              <span className="ml-2 normal-case tracking-normal text-faint/70">
                · per print
              </span>
            </span>
            <span className="flex items-baseline gap-2">
              <ThesisFlag thesis={thesis} />
              {fundamental?.risk != null && (
                <span className="font-mono text-[11px] text-caution">
                  risk {String(fundamental.risk).replace(/_/g, ' ')}
                </span>
              )}
              <Fresh
                date={fundamental?.data_as_of ? String(fundamental.data_as_of) : null}
                warnDays={120}
                prefix="last report "
              />
            </span>
          </div>
          {lastPrint && lpVerdict && (
            <div className="pt-2 text-[11px] font-mono text-muted">
              last print {String(lastPrint.earnings_date).slice(0, 10)}
              {lastPrint.eps_actual != null && (
                <>
                  {' · EPS '}{Number(lastPrint.eps_actual)}
                  {lastPrint.eps_estimate != null &&
                    ` vs ${Number(lastPrint.eps_estimate)}`}
                  {lastPrint.surprise_percentage != null &&
                    ` (${Number(lastPrint.surprise_percentage) > 0 ? '+' : ''}${Number(lastPrint.surprise_percentage).toFixed(0)}%)`}
                </>
              )}
              {lastPrint.revenue_actual != null && lastPrint.revenue_estimate != null && (
                <>
                  {' · rev '}{(Number(lastPrint.revenue_actual) / 1e9).toFixed(2)}B
                  {` vs ${(Number(lastPrint.revenue_estimate) / 1e9).toFixed(2)}B`}
                  {` (${((Number(lastPrint.revenue_actual) - Number(lastPrint.revenue_estimate)) / Math.abs(Number(lastPrint.revenue_estimate)) * 100) > 0 ? '+' : ''}${((Number(lastPrint.revenue_actual) - Number(lastPrint.revenue_estimate)) / Math.abs(Number(lastPrint.revenue_estimate)) * 100).toFixed(1)}%)`}
                </>
              )}
              {lastPrint.adjusted_eps_actual != null &&
                ` · adj ${Number(lastPrint.adjusted_eps_actual).toFixed(2)} ex-1x`}
              {' — '}
              <span className={lpTone}>{lpVerdict}</span>
              {Array.isArray(lastPrint.drivers) && (lastPrint.drivers as Record<string, unknown>[]).some(d => d?.delta_dir === 'cut' || d?.delta_dir === 'raised') && (
                <div className="pt-1">
                  {(lastPrint.drivers as Record<string, unknown>[])
                    .filter(d => d?.delta_dir === 'cut' || d?.delta_dir === 'raised')
                    .slice(0, 3)
                    .map((d, i) => (
                      <span key={i} className={d.delta_dir === 'cut' ? 'text-defensive' : 'text-aggressive'}>
                        {i > 0 && ' · '}{String(d.metric)} {String(d.period)} guide {String(d.delta_dir)}
                        {d.delta_pct != null && ` ${(Number(d.delta_pct) * 100).toFixed(0)}%`}
                      </span>
                    ))}
                </div>
              )}
              {lastPrint.narrative != null && (
                <div className="pt-1.5 font-sans text-[12px] leading-relaxed text-muted whitespace-pre-line">
                  {String(lastPrint.narrative)}
                </div>
              )}
            </div>
          )}
          <div className="pt-3">
            {obj(fundamental?.detail) ? (
              <FundPanel d={{
                ...(obj(fundamental?.detail) ?? {}),
                state: fundamental?.state,
              }} />
            ) : (
              <div className={`text-sm font-medium ${stateTone(fundamental?.state)}`}>
                {String(fundamental?.state ?? '—')}
              </div>
            )}
            <ThesisReport report={thesis?.report ?? null} />
          </div>
        </div>
        <div className="rounded-xl border border-hairline bg-card px-5 py-4 lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Tape
              <span className="ml-2 normal-case tracking-normal text-faint/70">
                · daily
              </span>
            </span>
            {technical?.as_of != null && (
              <span className="font-mono text-[11px] text-faint">
                {String(technical.as_of).slice(0, 10)}
              </span>
            )}
          </div>
          <div className="pt-3">
            {obj(technical?.detail) ? (
              <TapePanel
                d={{
                  ...(obj(technical?.detail) ?? {}),
                  state: technical?.state,
                }}
                spot={Number.isFinite(Number(card.spot)) ? Number(card.spot) : undefined}
              />
            ) : (
              <div className={`text-sm font-medium ${stateTone(technical?.state)}`}>
                {String(technical?.state ?? '—')}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* AI capex */}
      <div className="mt-2 rounded-xl border border-hairline bg-card px-5 py-3.5 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          AI capex
        </span>
        {capex ? (
          <>
            <span className="text-sm font-medium text-ink">
              {String(capex.exposure ?? capex.bucket ?? capex.category ?? 'tracked')}
            </span>
            <span className="text-xs text-muted">
              cycle {String(capex.band ?? '—')}
              {capex.score != null && ` ${String(capex.score)}/100`}
            </span>
          </>
        ) : (
          <span className="text-sm text-muted">not in a capex basket</span>
        )}
      </div>

      {/* SEC filings — backlog, goodwill, cash quality, split check */}
      {sec && (
        <div className="mt-2 rounded-xl border border-hairline bg-card px-5 py-3.5">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              SEC filings
            </span>
            {sec.rpo != null && (
              <span className="text-sm text-ink font-mono">
                backlog ${(Number(sec.rpo) / 1e9).toFixed(1)}B
                {sec.rpo_yoy != null && (
                  <span className={Number(sec.rpo_yoy) < 0 ? 'text-defensive' : 'text-aggressive'}>
                    {' '}{(Number(sec.rpo_yoy) * 100) >= 0 ? '+' : ''}{(Number(sec.rpo_yoy) * 100).toFixed(0)}% yoy
                  </span>
                )}
              </span>
            )}
            {sec.crpo != null && (
              <span className="text-sm text-muted font-mono">
                cRPO ${(Number(sec.crpo) / 1e9).toFixed(1)}B
                {sec.crpo_share != null && ` (${(Number(sec.crpo_share) * 100).toFixed(0)}% of backlog)`}
              </span>
            )}
            {sec.def_rev_yoy != null && (
              <span className={`text-sm font-mono ${Number(sec.def_rev_yoy) < -0.05 ? 'text-defensive' : 'text-muted'}`}>
                deferred rev {(Number(sec.def_rev_yoy) * 100) >= 0 ? '+' : ''}{(Number(sec.def_rev_yoy) * 100).toFixed(0)}% yoy
              </span>
            )}
            {sec.gw_impair_fy != null && Number(sec.gw_impair_fy) > 0 && (
              <span className="text-xs text-caution">
                goodwill impairment ${(Number(sec.gw_impair_fy) / (Number(sec.gw_impair_fy) >= 1e9 ? 1e9 : 1e6)).toFixed(1)}{Number(sec.gw_impair_fy) >= 1e9 ? 'B' : 'M'} — prior deal wrote off
              </span>
            )}
            {sec.fcf_ttm != null && (
              <span className={`text-sm font-mono ${Number(sec.fcf_ttm) < 0 ? 'text-defensive' : 'text-muted'}`}>
                FCF ${(Number(sec.fcf_ttm) / 1e9).toFixed(1)}B
                {sec.fcf_margin != null && ` (${(Number(sec.fcf_margin) * 100).toFixed(0)}%)`}
              </span>
            )}
            {sec.goodwill_assets_pct != null && Number(sec.goodwill_assets_pct) > 0.1 && (
              <span className="text-sm text-muted font-mono">
                goodwill {(Number(sec.goodwill_assets_pct) * 100).toFixed(0)}% of assets
              </span>
            )}
            {sec.acq_rev_pct != null && Number(sec.acq_rev_pct) > 0.10 && (
              <span className="text-xs text-caution">
                acq spend ~{(Number(sec.acq_rev_pct) * 100).toFixed(0)}% of rev — organic share unverifiable
              </span>
            )}
            {sec.split_suspect != null && Boolean(sec.split_suspect) && (
              <span className="text-xs text-defensive font-medium">
                ⚠ share-count step {sec.shares_step_ratio != null ? `${Number(sec.shares_step_ratio).toFixed(1)}×` : ''} — split detected; per-share history on mixed basis
              </span>
            )}
            {sec.as_of != null && (
              <span className="ml-auto font-mono text-[11px] text-faint">
                facts thru {String(sec.as_of).slice(0, 10)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* latest review — the standing 5 questions */}
      {review && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Latest review
              {review.trigger != null && (
                <span className="ml-2 normal-case tracking-normal text-faint">
                  {String(review.trigger)} · {String(review.as_of ?? '').slice(0, 10)}
                </span>
              )}
            </span>
            {review.verdict != null && (
              <span className={`text-sm font-medium ${stateTone(review.verdict)}`}>
                {String(review.verdict)}
                {review.score != null && (
                  <span className="ml-1 font-mono text-[11px] text-faint">
                    {Number(review.score) >= 0 ? '+' : ''}{Number(review.score).toFixed(1)}
                  </span>
                )}
              </span>
            )}
          </div>
          <div className="pt-3 space-y-2.5">
            {(['q1', 'q2', 'q3', 'q4'] as const).map((q) => {
              const ans = obj((obj(review?.answers) ?? {})[q])
              const lines = Array.isArray(ans?.lines) ? ans.lines : []
              if (!lines.length) return null
              const label = { q1: 'what changed', q2: 'funding', q3: 'earnings outlook', q4: 'market read' }[q]
              return (
                <div key={q}>
                  <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
                  <ul className="pt-0.5 space-y-0.5 text-xs text-muted leading-relaxed">
                    {lines.slice(0, 4).map((l, i) => (
                      <li key={i}>{String(l)}</li>
                    ))}
                  </ul>
                </div>
              )
            })}
            {Array.isArray(review.reasons) && review.reasons.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-faint">action basis</div>
                <ul className="pt-0.5 space-y-0.5 text-xs text-muted leading-relaxed">
                  {(review.reasons as unknown[]).slice(0, 6).map((r, i) => (
                    <li key={i}>{String(r)}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* expandable depth */}
      <div className="mt-8">
        <Gate feature="detail_sections">
          <Suspense fallback={null}>
            <AlertsSection sym={sym} />
          </Suspense>
          {fvMethods.length > 0 && (
            <Section title="Valuation methods" subtitle={`${fvMethods.length} blended`}>
              <div className="divide-y divide-transparent">
                {fvMethods.map((m, i) => {
                  const ex = obj(m.explain)
                  const mScen = obj(m.scenarios)
                  const legs = ['bear', 'base', 'bull', 'explosive']
                    .filter((k) => ex?.[k] != null || mScen?.[k] != null)
                  return (
                    <div key={i} className="border-b border-hairline/60 py-2 last:border-0">
                      <div className="flex justify-between gap-4 text-sm">
                        <span className="text-muted">
                          {String(m.key ?? 'method') +
                            (m.w != null ? ` (w ${Number(m.w).toFixed(2)})` : '') +
                            (m.outlier ? ' ⚠ outlier' : '')}
                        </span>
                        <span className="font-mono text-ink">{money(m.fv)}</span>
                      </div>
                      {legs.length > 0 && (
                        <div className="pt-1 pl-4 space-y-0.5">
                          {new Set(legs.map((k) => ex?.[k])).size === 1 ? (
                            <div className="flex justify-between gap-4 text-[11px] font-mono text-faint">
                              <span>{legs.map((k) => mScen?.[k] != null ? `${k} ${money(mScen[k])}` : k).join(' · ')}</span>
                              <span className="text-right">{String(ex?.[legs[0]] ?? '')}</span>
                            </div>
                          ) : (
                            legs.map((k) => (
                              <div key={k} className="flex justify-between gap-4 text-[11px] font-mono text-faint">
                                <span>
                                  {k}
                                  {mScen?.[k] != null ? ` ${money(mScen[k])}` : ''}
                                </span>
                                <span className="text-right">{ex?.[k] != null ? String(ex[k]) : ''}</span>
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </Section>
          )}

          {(tailwinds.length > 0 || themes.length > 0) && (
            <Section title="Tailwinds & themes">
              <div className="flex flex-wrap gap-2">
                {tailwinds.slice(0, 12).map((t, i) => (
                  <Chip key={`t${i}`} label={fmtShort(t)} tone="ok" />
                ))}
                {themes.slice(0, 12).map((t, i) => (
                  <Chip key={`h${i}`} label={fmtShort(t)} />
                ))}
              </div>
            </Section>
          )}

          {fundamental?.detail != null && (
            <Section title="Fundamentals detail">
              <div className="divide-y divide-transparent">
                {Object.entries(obj(fundamental.detail) ?? {}).slice(0, 24).map(([k, v]) => (
                  <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
              </div>
            </Section>
          )}

          {technical?.detail != null && (
            <Section title="Tape detail">
              <div className="divide-y divide-transparent">
                {Object.entries(obj(technical.detail) ?? {}).slice(0, 24).map(([k, v]) => (
                  <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
              </div>
            </Section>
          )}
        </Gate>
      </div>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — evidence assembled, human decides</span>
        <span className="font-mono">{sym}</span>
      </footer>
    </main>
  )
}

/** AI research — journaled tailwind/strength scores with the
 *  component-level 'why'. Own fetch, streams in; null when the
 *  symbol hasn't been researched. */
async function ResearchSection({ sym }: { sym: string }) {
  const res = await api.researchReport(sym).catch(() => null)
  const run = res?.run
  if (!run) return null
  const tw = run.scores?.tailwind
  const bs = run.scores?.strength
  const comps = Object.entries(tw?.components ?? {})
    .sort((a, b) => (b[1]?.weight ?? 0) - (a[1]?.weight ?? 0))
    .filter(([, c]) => c?.note)
  const products = run.report?.products ?? []
  const gates = run.report?.hard_gates ?? []
  const tone = (v?: number | null) =>
    v == null ? 'text-faint'
      : v >= 70 ? 'text-aggressive' : v >= 50 ? 'text-caution' : 'text-defensive'
  return (
    <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          AI research
        </span>
        <div className="flex items-baseline gap-3">
          {run.as_of && <Fresh date={String(run.as_of)} />}
          <Link href="/research" className="text-[11px] text-faint hover:text-accent">
            board →
          </Link>
        </div>
      </div>

      <div className="pt-3 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div>
          <div className={`font-mono text-2xl font-semibold ${tone(run.ai_tailwind_score)}`}>
            {run.ai_tailwind_score != null ? Number(run.ai_tailwind_score).toFixed(0) : '—'}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-faint">
            AI tailwind
          </div>
        </div>
        <div>
          <div className={`font-mono text-2xl font-semibold ${tone(run.business_strength)}`}>
            {run.business_strength != null ? Number(run.business_strength).toFixed(0) : '—'}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-faint">
            business strength
          </div>
        </div>
        {run.recommendation && (
          <div className="ml-auto">
            <span className="rounded-full border border-hairline px-3 py-1 text-xs font-medium text-ink">
              {String(run.recommendation).replace(/_/g, ' ')}
            </span>
          </div>
        )}
      </div>

      {tw?.capped && (
        <p className="pt-2 text-xs text-caution">capped — {tw.capped}</p>
      )}
      {gates.length > 0 && (
        <p className="pt-2 text-xs text-defensive">
          hard gates: {gates.join(', ').replace(/_/g, ' ')}
        </p>
      )}

      {/* the why — top-weighted component verdicts */}
      {comps.length > 0 && (
        <ul className="pt-3 space-y-1 text-xs text-muted leading-relaxed">
          {comps.slice(0, 6).map(([k, c]) => (
            <li key={k}>
              <span className="text-faint">{k.replace(/_/g, ' ')}</span>
              <span className="font-mono text-ink"> {c?.score}</span>
              <span className="text-faint">/{c?.weight}</span>
              {c?.note && <span> — {c.note}</span>}
            </li>
          ))}
        </ul>
      )}

      {products.length > 0 && (
        <div className="pt-3 border-t border-hairline/60 mt-3 flex flex-wrap gap-1.5">
          {products.slice(0, 8).map((p, i) => (
            <span key={i}
              className="rounded border border-hairline px-2 py-0.5 text-[10.5px] text-muted"
              title={p.why ?? ''}>
              {p.name}
              {p.stage && <span className="text-faint"> · {p.stage}</span>}
            </span>
          ))}
        </div>
      )}

      {tw?.coverage != null && (
        <p className="pt-3 text-[10px] text-faint">
          coverage {(tw.coverage * 100).toFixed(0)}%
          {run.rules_version && ` · ${run.rules_version}`}
        </p>
      )}
    </section>
  )
}

/** Short-positioning strip — own fetch, streams into the hero. */
async function SqueezeLine({ sym }: { sym: string }) {
  const squeeze = await api.shortSqueeze(sym).catch(() => null)
  if (!squeeze || squeeze.verdict === 'insufficient_data') return null
  return (
    <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
      <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
        shorts
      </span>
      {squeeze.si_pct != null && (
        <span className="font-mono text-muted">
          SI {squeeze.si_pct}% · {squeeze.days_to_cover ?? '?'}d cover
        </span>
      )}
      {squeeze.sv_ratio_latest != null && (
        <span className="font-mono text-muted">
          sv ratio {squeeze.sv_ratio_latest}%
          {squeeze.sv_trend != null && (
            <span className={squeeze.sv_trend <= -1 ? 'text-aggressive'
              : squeeze.sv_trend >= 1 ? 'text-defensive' : 'text-faint'}>
              {' '}{squeeze.sv_trend <= -1 ? '↓' : squeeze.sv_trend >= 1 ? '↑' : '→'}
            </span>
          )}
        </span>
      )}
      <span className={`font-medium ${squeeze.verdict === 'likely_covering' ? 'text-caution'
        : squeeze.verdict === 'new_shorts_pressing' ? 'text-defensive'
          : squeeze.verdict === 'squeeze_setup' ? 'text-accent'
            : squeeze.verdict === 'genuine_accumulation' ? 'text-aggressive'
              : 'text-faint'}`}>
        {squeeze.verdict === 'likely_covering'
          ? `⚠ covering rally${squeeze.covering_probability != null ? ` ${squeeze.covering_probability}%` : ''} — fade risk`
          : squeeze.verdict === 'new_shorts_pressing'
            ? '⚠ shorts pressing into strength'
            : squeeze.verdict === 'squeeze_setup'
              ? `⚡ squeeze fuel ${squeeze.fuel ?? '?'} — a real bid could trigger covering`
              : squeeze.verdict === 'genuine_accumulation'
                ? 'rally looks like real buying'
                : 'no clear short signal'}
      </span>
      {squeeze.data_quality === 'partial' && (
        <span className="text-faint">(partial data)</span>
      )}
    </div>
  )
}

/** Recent alerts — own fetch, streams into the depth area. */
async function AlertsSection({ sym }: { sym: string }) {
  const alerts = await api.alerts({ symbol: sym, hours: 168 })
    .catch(() => null)
  const items = alerts?.items ?? []
  if (items.length === 0) return null
  return (
    <Section title="Alerts on this name" subtitle="last 7 days" defaultOpen>
      <div className="divide-y divide-hairline/60">
        {items.slice(0, 8).map((a, i) => (
          <div key={a.id ?? i} className="py-2.5 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className={
                String(a.direction).toLowerCase() === 'negative'
                  ? 'text-defensive'
                  : String(a.direction).toLowerCase() === 'positive'
                    ? 'text-aggressive'
                    : 'text-ink'
              }>
                {a.title ?? '—'}
              </span>
              <span className="shrink-0 font-mono text-[11px] text-faint">
                {a.event_type != null &&
                  String(a.event_type).replace(/_/g, ' ')}
              </span>
            </div>
            {a.detail != null && (
              <div className="pt-0.5 text-xs text-muted">
                {fmtShort(a.detail).slice(0, 180)}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  )
}
