import Link from 'next/link'
import {
  api, type PlanSuggestion, type PlanRow, type SelloffCand,
  type BestPicks, type BestPick, type LevSwings, type LevEtf
} from '@/lib/api'
import { Gate } from '@/components/regime'
import { toneOf } from '@/components/signal-strip'
import { OpenPlanButton, ClosePlanButton } from '@/components/plan-entry'

const DOT: Record<string, string> = {
  ok: 'bg-aggressive', warn: 'bg-caution',
  bad: 'bg-defensive', off: 'bg-faint',
}

function money(v?: number | null, dec = 2) {
  return v != null && Number.isFinite(Number(v))
    ? `$${Number(v).toFixed(dec)}` : '—'
}

function StateDot({ v }: { v?: string | null }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${DOT[toneOf(v)]}`}
    />
  )
}

function ThesisDot({ s }: { s: PlanSuggestion }) {
  if (!s.thesis) return null
  return (
    <span className={`text-[11px] ${{
      ok: 'text-aggressive', warn: 'text-caution',
      bad: 'text-defensive', off: 'text-muted'
    }[toneOf(s.thesis)]
      }`}>
      {String(s.thesis).replace(/_/g, ' ')}
      {s.thesis_dir === 'up' ? ' ▲' : s.thesis_dir === 'down' ? ' ▼' : ''}
    </span>
  )
}

/** Levels text — enter / exit per instrument. */
function Levels({ s }: { s: PlanSuggestion }) {
  const parts: React.ReactNode[] = []
  const isOptionSell = s.use_case === 'csp' || s.use_case === 'covered_call'
  if (isOptionSell && s.strike != null) {
    parts.push(<span key="e" className="text-ink">sell @{money(s.strike)}</span>)
    parts.push(<span key="px" className="text-faint">px {money(s.spot)}</span>)
    if (s.collateral != null)
      parts.push(<span key="c">collat {money(s.collateral, 0)}</span>)
    if (s.contracts != null && s.contracts > 0)
      parts.push(<span key="n" className="text-ink">{s.contracts}ct</span>)
    if (s.shares != null) parts.push(<span key="sh">{s.shares}sh</span>)
    parts.push(<span key="x" className="text-aggressive">exit: {s.exit_rule}</span>)
  } else {
    const e = s.entry_px ?? s.spot
    if (e != null)
      parts.push(<span key="e" className="text-ink">in @{money(e)}</span>)
    if (s.stop_px != null)
      parts.push(<span key="s" className="text-defensive">stop {money(s.stop_px)}</span>)
    if (s.target_px != null)
      parts.push(<span key="t" className="text-aggressive">out {money(s.target_px)}</span>)
    if (s.rr != null)
      parts.push(<span key="r">R:R {Number(s.rr).toFixed(1)}</span>)
    if (s.dte || s.instrument?.startsWith('LEAP'))
      parts.push(<span key="d">{s.dte ?? '12–24mo'}</span>)
  }
  if (s.iv_hv != null)
    parts.push(
      <span key="iv" className={Number(s.iv_hv) >= 1 ? 'text-aggressive' : 'text-caution'}>
        iv/hv {s.iv_hv}
      </span>)
  return <>{parts}</>
}

function Pick({ s }: { s: PlanSuggestion }) {
  const thesis = [
    s.instrument, s.strike ? `strike ${money(s.strike)}` : null,
    s.dte, s.iv_hv != null ? `iv/hv ${s.iv_hv}` : null,
    s.thesis ? `thesis ${s.thesis}` : null,
  ].filter(Boolean).join(' · ')
  return (
    <div className="py-1">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {s.top && (
            <span className="text-aggressive font-bold text-[13px]"
              title={`top setup — conviction score ${s.pick_score}`}>★</span>
          )}
          <StateDot v={s.state ?? s.mom} />
          <Link href={`/stock?sym=${s.symbol}`}
            className="font-semibold text-[13px] text-ink hover:text-accent">
            {s.symbol}
          </Link>
          {s.intent && (
            <span className={`rounded-full border px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider ${s.intent === 'acquire' || s.intent === 'exit'
              ? 'border-caution/40 text-caution'
              : 'border-accent/40 text-accent'}`}>
              {s.intent}
            </span>
          )}
          <ThesisDot s={s} />
          {s.earn_days != null && s.earn_days >= 0 && s.earn_days <= 35 && (
            <span className="text-[10px] text-caution">⚠EPS{s.earn_days}d</span>
          )}
        </div>
        <OpenPlanButton
          draft={{
            symbol: s.symbol,
            use_case: s.use_case ?? 'swing',
            entry_px: s.entry_px ?? s.strike ?? s.spot,
            stop_px: (s.plan?.stop_px as number) ?? s.stop_px,
            target1_px: (s.plan?.target1_px as number) ?? s.target_px,
            target2_px: s.plan?.target2_px as number | undefined,
          }}
          thesis={thesis}
        />
      </div>
      <div className="pl-3 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
        <Levels s={s} />
      </div>
      {(s.flags ?? []).map((f, i) => (
        <div key={i} className="pl-3 text-[10px] text-caution">⚠ {f}</div>
      ))}
    </div>
  )
}

const LANE_DEFS: { key: string; label: string }[] = [
  { key: 'swing', label: 'swing' },
  { key: 'csp', label: 'cash-secured put' },
  { key: 'covered_call', label: 'covered call' },
  { key: 'leap_call', label: 'LEAP call' },
  { key: 'leap_put', label: 'LEAP put' },
]

const DEC_TONE: Record<string, string> = {
  priority: 'border-aggressive/50 text-aggressive',
  starter: 'border-aggressive/40 text-aggressive',
  watch: 'border-caution/40 text-caution',
  pass: 'border-hairline text-faint',
  reject: 'border-defensive/50 text-defensive',
}

const CLASS_LABEL: Record<string, string> = {
  macro_panic: 'macro panic',
  sector_contagion: 'sector contagion',
  positioning_unwind: 'positioning unwind',
  fundamental_repricing: 'repricing',
  structural_impairment: 'impaired',
  idiosyncratic_weakness: 'own-merits',
}

function SelloffRow({ c }: { c: SelloffCand }) {
  const tone = DEC_TONE[c.decision ?? 'pass'] ?? DEC_TONE.pass
  return (
    <div className="border-t border-hairline/50 py-2 first:border-0">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          <span className={`rounded-full border px-2 py-px font-mono text-[11px] font-semibold ${tone}`}>
            {c.score}
          </span>
          <Link href={`/stock?sym=${c.symbol}`}
            className="font-semibold text-[13px] text-ink hover:text-accent">
            {c.symbol}
          </Link>
          <span className={`text-[10px] uppercase tracking-wider ${c.classification === 'macro_panic' || c.classification === 'sector_contagion'
            ? 'text-aggressive'
            : c.classification === 'structural_impairment' || c.classification === 'fundamental_repricing'
              ? 'text-defensive' : 'text-caution'}`}>
            {CLASS_LABEL[c.classification ?? ''] ?? c.classification}
          </span>
          {c.sbd?.class && (
            <span title={`business ${c.business_bucket ?? '?'} · ${c.pf_gap_note ?? 'gap unverified'}`}
                  className={`rounded px-1.5 py-px text-[9px] font-medium uppercase tracking-wider ${
              c.sbd.class === 'beat_down_stock' || c.sbd.class === 'confirmed_recovery_candidate'
                ? 'bg-aggressive/15 text-aggressive'
                : c.sbd.class === 'beat_down_business' || c.sbd.class === 'structural_risk'
                  ? 'bg-defensive/15 text-defensive'
                  : 'bg-hairline/60 text-muted'}`}>
              {(c.sbd.class ?? '').replace(/_/g, ' ')}
            </span>
          )}
          {(c.bucket_notes ?? []).includes('fundamental_contradiction') && (
            <span title="weak score but journaled fundamentals look strong — flagged for review"
                  className="rounded bg-caution/15 px-1.5 py-px text-[9px] font-medium uppercase tracking-wider text-caution">
              contradict
            </span>
          )}
          <span className="text-[10px] text-faint">{c.tier}</span>
          {c.thesis && (
            <span className="text-[10px] text-muted">
              thesis {c.thesis}
            </span>
          )}
        </div>
        <span className={`text-[10px] uppercase tracking-wider ${tone.split(' ')[1]}`}>
          {c.decision}
        </span>
      </div>
      <div className="pl-1 pt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
        {c.rel_5d != null && <span>rel5 {(c.rel_5d * 100).toFixed(1)}%</span>}
        {c.dd_60d != null && <span>dd {(c.dd_60d * 100).toFixed(0)}%</span>}
        {c.pf_gap != null && (
          <span title="price-fundamental gap — drawdown minus estimate deterioration; deeper = more dislocated"
                className={c.pf_gap <= -0.15 ? 'text-aggressive' : ''}>
            gap {(c.pf_gap * 100).toFixed(0)}%
          </span>
        )}
        {c.rsi != null && <span>rsi {c.rsi}</span>}
        <span>{c.mom}</span>
        {c.sq_verdict === 'likely_covering' && (
          <span className="text-caution" title="bounce is short covering — fade risk, not durable stabilization">⚠covering</span>
        )}
        {c.sq_verdict === 'new_shorts_pressing' && (
          <span className="text-defensive" title="short-sale ratio rising — shorts pressing into strength">⚠pressing</span>
        )}
        {c.sq_verdict === 'squeeze_setup' && (
          <span className="text-accent" title={`heavily shorted + stabilizing — fuel ${c.sq_fuel ?? '?'}`}>⚡fuel</span>
        )}
        {c.fv != null && c.close != null && (
          <span className="text-aggressive">
            fv {money(c.fv)} ({c.fv_upside != null ? `+${Number(c.fv_upside).toFixed(0)}%` : ''})
          </span>
        )}
        {c.invalidation != null && (
          <span className="text-defensive">invalid &lt;{money(c.invalidation)}</span>
        )}
        {c.earn_days != null && c.earn_days <= 35 && c.earn_days >= 0 && (
          <span className="text-caution">⚠EPS{c.earn_days}d</span>
        )}
      </div>
      {c.reason && (
        <div className="pl-1 pt-0.5 text-[10px] text-muted">
          {c.reason}
        </div>
      )}
      {c.action && c.decision !== 'pass' && c.decision !== 'reject' && (
        <div className="pl-1 pt-0.5 text-[10px] text-faint">
          {c.action}
          {c.entry_plan?.stages && (
            <span className="text-faint">
              {' '}· stages 25/25/25/25: {c.entry_plan.stages[0]?.trigger}
            </span>
          )}
        </div>
      )}
      {(c.gates ?? []).map((g, i) => (
        <div key={i} className="pl-1 pt-0.5 text-[10px] text-caution">⚠ {g}</div>
      ))}
    </div>
  )
}

/* ---- best picks — the three-lane ranked research shortlist ---- */

const TIER_TONE: Record<string, string> = {
  A: 'border-aggressive/50 text-aggressive',
  B: 'border-accent/40 text-accent',
  C: 'border-caution/40 text-caution',
  X: 'border-hairline text-faint',
}

const BP_LANES: { key: string; label: string }[] = [
  { key: 'growth_swing', label: 'growth swing' },
  { key: 'long_term', label: 'long term' },
  { key: 'compounder_3_5y', label: 'compounder 3–5y' },
]

function BpRow({ p }: { p: BestPick }) {
  const tone = TIER_TONE[p.tier ?? 'X'] ?? TIER_TONE.X
  return (
    <div className="py-1.5">
      <div className="flex items-baseline gap-2 min-w-0">
        <span className={`rounded-full border px-1.5 py-px font-mono text-[10px] font-bold ${tone}`}>
          {p.tier}
        </span>
        <Link href={`/stock?sym=${p.symbol}`}
          className="font-semibold text-[13px] text-ink hover:text-accent">
          {p.symbol}
        </Link>
        <span className="font-mono text-[11px] text-muted">
          {p.score != null ? Math.min(100, Math.max(0, Number(p.score))).toFixed(0) : '—'}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-faint">
          {p.label}
        </span>
        {(p.routing ?? []).map((r) => (
          <span key={r}
            className="rounded-full border border-caution/40 px-1.5 py-px text-[9px] text-caution">
            {r.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      <div className="pl-1 pt-0.5 flex flex-wrap gap-x-3 font-mono text-[10px] text-muted">
        {p.px != null && <span>px {money(p.px)}</span>}
        <span>{p.mom}</span>
        <span>{p.fund}</span>
        {p.fv != null && (
          <span className="text-aggressive">
            fv {Number(p.fv) >= 0 ? '+' : ''}{Number(p.fv).toFixed(0)}%
            {p.fv_reliability === 'single' && (
              <span className="text-caution" title="single-method FV — not corroborated">¹</span>
            )}
          </span>
        )}
        {p.selloff && (
          <span className="text-accent">
            {CLASS_LABEL[p.selloff] ?? p.selloff}
          </span>
        )}
      </div>
      {p.reason && (
        <div className="pl-1 pt-0.5 text-[10px] text-faint">{p.reason}</div>
      )}
    </div>
  )
}

function BestPicksSection({ bp }: { bp: BestPicks | null }) {
  const secs = bp?.sections ?? {}
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Best picks
        </span>
        <span className="text-[11px] text-faint">
          {bp?.as_of ? `as of ${bp.as_of}` : 'no eval yet — runs post-refresh'}
          {bp?.evaluated != null && ` · ${bp.evaluated} names`}
        </span>
      </div>
      {!bp?.as_of ? (
        <p className="pt-2 text-xs text-muted">
          no best-picks eval journaled yet — the daily job scores the
          active tier across all three horizons.
        </p>
      ) : (
        <div className="grid gap-4 pt-2 lg:grid-cols-3">
          {BP_LANES.map(({ key, label }) => {
            const sec = secs[key]
            const picks = sec?.picks ?? []
            const watch = sec?.watch ?? []
            return (
              <div key={key}>
                <div className="flex items-baseline justify-between">
                  <span className="text-[10px] uppercase tracking-wider text-faint">
                    {label}
                  </span>
                  <span className="text-[10px] text-faint">
                    {sec?.horizon}
                  </span>
                </div>
                <div className="divide-y divide-hairline/40">
                  {picks.map((p) => <BpRow key={p.symbol} p={p} />)}
                  {picks.length === 0 && (
                    <p className="py-1 pl-1 text-[11px] text-faint">
                      nothing qualified — fine
                    </p>
                  )}
                </div>
                {watch.length > 0 && (
                  <div className="pt-1 border-t border-hairline/40">
                    <div className="text-[9px] uppercase tracking-wider text-faint">
                      watch
                    </div>
                    <div className="pt-0.5 flex flex-wrap gap-x-2 text-[11px]">
                      {watch.map((w) => (
                        <Link key={w.symbol}
                          href={`/stock?sym=${w.symbol}`}
                          className="text-muted hover:text-accent"
                          title={w.reason ?? ''}>
                          {w.symbol}
                          <span className="text-faint">
                            {w.routing?.length
                              ? ` (${w.routing.join('+').replace(/_/g, ' ')})`
                              : ''}
                          </span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      <p className="pt-2 text-[10px] text-faint">
        ranked research shortlist — A/B are pick-eligible, watch is the
        research lane; gated names never occupy a slot. Advisory until
        out-of-sample grading proves the tiers separate.
      </p>
    </section>
  )
}

const LEV_STATE: Record<string, string> = {
  triggered: 'text-aggressive border-aggressive/40',
  armed: 'text-caution border-caution/40',
  vetoed: 'text-defensive border-defensive/40',
  flat: 'text-faint border-hairline',
}

const LEV_DESC: Record<string, string> = {
  SOXS: 'fade the extension — index RSI hot + 8EMA break',
  SOXL: 'confirmed rebound — index RSI washed out + reclaim',
}

const LEV_STATE_DESC: Record<string, string> = {
  flat: "premise doesn't exist → do nothing (the default)",
  armed: 'premise exists, entry unconfirmed → watch, don\u2019t buy yet',
  vetoed: 'setup killed by counter-evidence → do nothing',
  error: 'index data missing or stale → no signal',
}

function levStateDesc(row: LevEtf): string {
  if (row.state === 'triggered') {
    return row.actionable
      ? 'confirmed + priceable → candidate entry — review the levels'
      : 'confirmed, but unplannable (missing data or bad stop) → do nothing'
  }
  return LEV_STATE_DESC[row.state] ?? LEV_STATE_DESC.flat
}

const HOLD_TONE: Record<string, string> = {
  exit: 'text-defensive',
  'take profits': 'text-caution',
  hold: 'text-aggressive',
  watch: 'text-faint',
}

const HOLD_DESC: Record<string, string> = {
  exit: 'sell — thesis invalidated or the tape healed',
  'take profits': 'sell into the move — it matured, bank it',
  hold: 'thesis still working — sit',
  watch: 'no clear verdict — neither working nor broken',
}

function LevCard({ etf, row }: { etf: string; row: LevEtf }) {
  const lv = row.levels ?? {}
  const idx = row.index ?? {}
  const hard = row.checklist?.filter((c) => !c.soft) ?? []
  const soft = row.checklist?.filter((c) => c.soft) ?? []
  const passed = hard.filter((c) => c.ok).length
  return (
    <div className="rounded-lg border border-hairline/60 px-4 py-3">
      <div className="flex items-baseline justify-between">
        <div>
          <span className="font-semibold text-ink">{etf}</span>
          <span className="pl-2 text-[10px] text-faint">{LEV_DESC[etf]}</span>
        </div>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${LEV_STATE[row.state] ?? LEV_STATE.flat}`}>
          {row.state}{row.persisting ? ' ↺' : ''}
        </span>
      </div>
      <p className="pt-0.5 text-[10px] text-faint">
        {levStateDesc(row)}
        {row.persisting && ' · same setup as yesterday — not a fresh signal'}
      </p>
      <div className="pt-1 text-[10px] font-mono text-muted">
        {idx.rsi != null && `idx rsi ${idx.rsi} `}
        {idx.vs50 != null && `· ${(idx.vs50 * 100).toFixed(0)}% vs 50d `}
        {idx.soxx_close != null && `· soxx ${idx.soxx_close} `}
        {hard.length > 0 && `· ${passed}/${hard.length} legs`}
      </div>
      {row.state !== 'flat' && (
        <div className="pt-1.5 divide-y divide-hairline/30">
          {[...hard, ...soft].map((c, i) => (
            <div key={i}
              className={`flex gap-1.5 py-0.5 text-[11px] ${c.soft ? 'text-faint' : c.ok ? 'text-muted' : 'text-defensive/80'}`}>
              <span className="w-3 shrink-0">{c.ok ? '✓' : '✗'}</span>
              <span>{c.line}</span>
            </div>
          ))}
        </div>
      )}
      {row.veto && (
        <p className="pt-1 text-[11px] text-defensive">veto — {row.veto}</p>
      )}
      {row.warn && (
        <p className="pt-1 text-[11px] text-caution">⚠ {row.warn}</p>
      )}
      {row.state === 'triggered' && row.actionable === false && (
        <p className="pt-1 text-[11px] text-defensive">
          not actionable — {row.state_note ?? 'required data or priceable stop missing'}
        </p>
      )}
      {row.actionable && lv.entry != null && (
        <div className="pt-1.5 text-[10px] font-mono text-muted">
          {money(lv.entry)} → stop {money(lv.stop)}
          {' '}(idx {money(lv.idx_stop, 1)}
          {lv.implied_loss_pct != null &&
            ` / −${(lv.implied_loss_pct * 100).toFixed(0)}%`})
          {lv.t1 != null && ` · t1 ${money(lv.t1)}`}
          {lv.t1_frac != null && `(${Math.round(lv.t1_frac * 100)}%)`}
          {lv.t2 != null && ` · t2 ${money(lv.t2)}`}
          {lv.shares != null && (
            <span className="text-faint">
              {' '}· {lv.shares}sh risks {money(lv.risk_usd, 0)}
              {lv.notional_capped ? ' · capped' : ''}
            </span>
          )}
        </div>
      )}
      {row.actionable && row.state_note && (
        <p className="pt-0.5 text-[10px] text-faint">{row.state_note}</p>
      )}
      {row.position && (
        <div className="pt-1.5 mt-1 border-t border-hairline/40">
          <div className="flex items-baseline gap-2 text-[11px]">
            <span className="text-[9px] uppercase tracking-wider text-faint">
              position
            </span>
            <span className="font-mono text-muted">
              {money(row.position.entry)} → {money(row.position.px)}
            </span>
            {row.position.unrealized_r != null && (
              <span className={`font-mono ${row.position.unrealized_r >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                {row.position.unrealized_r >= 0 ? '+' : ''}
                {row.position.unrealized_r}R
              </span>
            )}
            {row.position.state === 'closed' && row.position.realized_r != null && (
              <span className={`font-mono ${row.position.realized_r >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                closed {row.position.realized_r >= 0 ? '+' : ''}
                {row.position.realized_r}R · {row.position.exit_reason}
              </span>
            )}
          </div>
          <div className="pt-0.5 text-[10px] text-faint">
            trail {money(row.position.stop)}
            {row.position.partials ? ` · ${row.position.partials}/2 partials` : ''}
            {row.position.banked_r ? ` · banked +${row.position.banked_r}R` : ''}
            {row.position.bars_held != null && ` · day ${row.position.bars_held}`}
          </div>
        </div>
      )}
      {row.hold && (
        <div className="pt-1.5 mt-1 border-t border-hairline/40">
          <div className="flex items-baseline gap-2 text-[11px]">
            <span className="text-[9px] uppercase tracking-wider text-faint">
              holding?
            </span>
            <span className={HOLD_TONE[row.hold.verdict] ?? 'text-faint'}>
              {row.hold.verdict}
            </span>
            <span className="text-[10px] text-faint">
              {HOLD_DESC[row.hold.verdict] ?? ''}
            </span>
            {row.hold.days != null && row.hold.days > 1 && (
              <span className="text-[10px] text-faint">
                day {row.hold.days} in-state
              </span>
            )}
          </div>
          {row.hold.time_stop && (
            <p className="pt-0.5 text-[10px] text-defensive">
              {row.hold.time_stop}
            </p>
          )}
          {(row.hold.why ?? []).map((w, i) => (
            <p key={i} className="pt-0.5 text-[10px] text-faint">
              {w.line}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function LevSwingsSection({ ls }: { ls: LevSwings | null }) {
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          3× semis swing — candidates
        </span>
        <span className="text-[11px] text-faint">
          {ls?.as_of ? `${ls.signal_src} tape ${ls.as_of}` : 'no eval yet'}
          {ls?.risk_pct != null && ` · risk ${(ls.risk_pct * 100).toFixed(2)}%`}
        </span>
      </div>
      <p className="pt-1 text-[10px] text-faint">
        a card is a candidate only when it reads <b className="text-muted">triggered</b> and
        shows entry/stop levels — <b className="text-muted">armed</b>,{' '}
        <b className="text-muted">flat</b> and <b className="text-muted">vetoed</b> all mean
        do nothing
      </p>
      {ls?.error ? (
        <p className="pt-2 text-xs text-muted">{ls.error}</p>
      ) : (
        <div className="grid gap-3 pt-2 lg:grid-cols-2">
          {(['SOXS', 'SOXL'] as const).map((e) =>
            ls?.etfs?.[e]
              ? <LevCard key={e} etf={e} row={ls.etfs[e]} />
              : <div key={e} className="text-xs text-faint">{e} — no data</div>)}
        </div>
      )}
      <p className="pt-2 text-[10px] text-faint">
        {ls?.caveat ??
          'hypothesis under test — journaled for grading before any size'}
      </p>
    </section>
  )
}

const PLAN_ICON: Record<string, string> = {
  stop_hit: '🔴', invalidated: '🔴', target2_hit: '🟢',
  extended: '🟡', stalled: '🟠', trail_up: '🔵',
  target1_hit: '🟡', on_track: '⚪',
}

export default async function PlanPage({
  searchParams,
}: {
  searchParams: { funds?: string }
}) {
  const funds = searchParams.funds ? Number(searchParams.funds) : undefined
  const [plan, open, so, bp, ls] = await Promise.all([
    api.incomePlan(funds),
    api.tradePlans(),
    api.selloff(),
    api.bestPicks(),
    api.levSwings(funds),
  ])
  const sectors = plan?.sectors ?? []
  const pos = plan?.posture ?? {}
  const noLongs = pos.new_longs === false
  const openPlans = open?.open ?? []
  const closedPlans = open?.closed ?? []
  const outcomes = open?.outcomes
  return (
    <main className="mx-auto max-w-6xl px-5 pb-20">
      <header className="pt-6 pb-6">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Trading plan
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Today&apos;s <span className="text-accent">plan</span>
        </h1>
        <div className="pt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 ${noLongs ? 'text-defensive' : 'text-muted'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${noLongs ? 'bg-defensive' : 'bg-aggressive'}`} />
            posture {String(pos.posture ?? '—')}
            {pos.regime_as_of && (
              <span className="text-faint">· {String(pos.regime_as_of).slice(0, 10)}</span>
            )}
          </span>
          {plan?.bias && plan.bias !== 'neutral' && (
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${plan.bias === 'fear'
              ? 'border-aggressive/40 text-aggressive'
              : 'border-caution/40 text-caution'}`}>
              {plan.bias === 'fear' ? '↯ be greedy' : '☂ be fearful'}
            </span>
          )}
          {(() => {
            const fl: string[] = pos.flags ?? []
            const cr = fl.find((f: string) => f.startsWith('credit_'))
            return cr ? (
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${cr === 'credit_severe'
                ? 'border-defensive/40 text-defensive'
                : cr === 'credit_stress' ? 'border-caution/40 text-caution'
                  : 'border-hairline text-faint'}`}
                title={String(pos.credit_note ?? '')}>
                credit {cr.replace('credit_', '')}
                {pos.evidence?.credit_confidence ? (
                  <span className="text-faint">· {String(pos.evidence.credit_confidence as string)}</span>
                ) : null}
              </span>
            ) : null
          })()}
          {noLongs && (
            <span className="text-defensive text-[11px]">
              swings gated — contrarian lanes stay open
            </span>
          )}
          {funds != null ? (
            <span className="font-mono text-muted">
              funds ${funds.toLocaleString()}
              <Link href="/plan" className="ml-2 text-faint hover:text-accent">✕</Link>
            </span>
          ) : (
            <Link href="/plan?funds=50000" className="text-accent underline underline-offset-2">
              set funds to size contracts → ?funds=50000
            </Link>
          )}
        </div>
        {plan?.bias_note && (
          <p className="pt-2 max-w-xl text-xs text-muted">{plan.bias_note}</p>
        )}
        <p className="pt-1 max-w-xl text-xs text-faint">
          <span className="text-aggressive font-bold">★</span> today's
          top 3–4 setups — highest conviction across all lanes
          (thesis + tape + fundamentals + premium, flags penalized)
        </p>
        {plan?.note && (
          <p className="pt-1 max-w-xl text-xs text-faint">{plan.note}</p>
        )}
      </header>

      <Gate feature="board">
        {/* selloff engine — dip vs deterioration */}
        <section className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Selloff engine
            </span>
            <span className={`text-[11px] font-mono ${so?.market?.level === 'severe' ? 'text-defensive'
              : so?.market?.level === 'mild' ? 'text-caution'
                : 'text-faint'}`}>
              {so?.market?.level ?? '—'} dislocation
              {so?.market?.breadth_score != null &&
                ` · breadth ${so.market.breadth_score.toFixed(0)}`}
              {so?.market?.spy_5d != null &&
                ` · spy5d ${(so.market.spy_5d * 100).toFixed(1)}%`}
              {so?.as_of && (
                <span className="text-faint">
                  {' '}· ran {so.as_of}
                </span>
              )}
            </span>
          </div>
          <div className="pt-2">
            {(so?.candidates ?? []).filter((c) => c.decision !== 'reject')
              .slice(0, 10)
              .map((c) => <SelloffRow key={c.symbol} c={c} />)}
            {(so?.candidates ?? []).length === 0 && (
              <p className="text-xs text-muted">
                no fallen-but-sound names right now — a selloff isn't
                automatically an opportunity
              </p>
            )}
          </div>
        </section>

        <BestPicksSection bp={bp} />

        <LevSwingsSection ls={ls} />

        {sectors.length === 0 && (
          <div className="rounded-xl border border-hairline bg-card px-5 py-8 text-center">
            <p className="text-sm text-muted">
              no sector qualified today — no-trade is a valid plan
            </p>
          </div>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          {sectors.map(({ sector, lanes }) => (
            <section key={sector}
              className="rounded-xl border border-hairline bg-card px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                  {sector}
                </span>
                <span className="text-[11px] text-faint">
                  top 3 per lane
                </span>
              </div>
              <div className="pt-2 space-y-3">
                {LANE_DEFS.map(({ key, label }) => {
                  const items = (lanes as Record<string, PlanSuggestion[]>)[key] ?? []
                  return (
                    <div key={key}>
                      <div className="text-[10px] uppercase tracking-wider text-faint">
                        {label}
                      </div>
                      {items.length === 0 ? (
                        <div className="py-1 pl-3 text-[11px] text-faint">—</div>
                      ) : (
                        <div className="divide-y divide-hairline/40">
                          {items.map((s) => (
                            <Pick key={s.symbol + key} s={s} />
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}
        </div>

        {/* open plans — the tracked book */}
        <section className="mt-4 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Open plans
            </span>
            <span className="text-[11px] text-faint">
              status re-evaluates live — you close the trade
            </span>
          </div>
          <div className="pt-2 divide-y divide-hairline/60">
            {openPlans.length === 0 && (
              <p className="py-3 text-xs text-muted">
                no open plans — open one above; it gets tracked against
                its stop/targets/trail daily.
              </p>
            )}
            {openPlans.map((p: PlanRow) => {
              const st = p.eval?.status ?? p.last_status ?? 'on_track'
              return (
                <div key={p.id} className="py-2.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="flex items-baseline gap-2 text-sm min-w-0">
                      <span>{PLAN_ICON[st] ?? '⚪'}</span>
                      <Link href={`/stock?sym=${p.symbol}`}
                        className="font-semibold text-ink hover:text-accent">
                        {p.symbol}
                      </Link>
                      <span className="text-[10px] uppercase tracking-wider text-faint">
                        {p.use_case} {p.direction === 'short' ? '· short' : ''}
                      </span>
                      <span className="font-mono text-xs text-muted">
                        entry {money(p.entry_px)} · px {money(p.px)}
                        {p.r != null && (
                          <span className={Number(p.r) >= 0 ? 'text-aggressive' : 'text-defensive'}>
                            {' '}{Number(p.r) >= 0 ? '+' : ''}{Number(p.r).toFixed(1)}R
                          </span>
                        )}
                        {p.days != null && <span> · {p.days}d</span>}
                      </span>
                    </div>
                    <ClosePlanButton id={p.id} px={p.px} />
                  </div>
                  {p.eval?.action_hint && p.eval.action_hint !== 'hold' && (
                    <div className="pt-0.5 text-[11px] text-caution">
                      {p.eval.action_hint} — {p.eval.why}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        {/* track record — the closed loop: what the plans actually paid */}
        <section className="mt-4 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Track record
            </span>
            <span className="text-[11px] text-faint">
              closed plans graded vs entry risk — the feedback loop
            </span>
          </div>
          {outcomes?.n ? (
            <>
              <div className="pt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ['plans closed', outcomes.n],
                  ['win rate', outcomes.by_use_case?.length
                    ? `${Math.round((outcomes.by_use_case.reduce(
                      (a, b) => a + (b.win_rate ?? 0) * (b.n ?? 0), 0)
                      / outcomes.n) * 100)}%` : '—'],
                  ['avg R', outcomes.by_use_case?.length
                    ? `${(outcomes.by_use_case.reduce(
                      (a, b) => a + (b.avg_r ?? 0) * (b.n ?? 0), 0)
                      / outcomes.n).toFixed(2)}R` : '—'],
                  ['avg days', outcomes.by_use_case?.length
                    ? Math.round(outcomes.by_use_case.reduce(
                      (a, b) => a + (b.avg_days ?? 0) * (b.n ?? 0), 0)
                      / outcomes.n) : '—'],
                ].map(([l, v]) => (
                  <div key={String(l)}
                    className="rounded-lg border border-hairline/60 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wider text-faint">{l}</div>
                    <div className="pt-0.5 font-mono text-sm text-ink">{String(v)}</div>
                  </div>
                ))}
              </div>
              <div className="pt-3 overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-left text-faint">
                      <th className="py-1 pr-3 font-normal">lane</th>
                      <th className="py-1 pr-3 font-normal text-right">n</th>
                      <th className="py-1 pr-3 font-normal text-right">win</th>
                      <th className="py-1 pr-3 font-normal text-right">avg R</th>
                      <th className="py-1 pr-3 font-normal text-right">t1</th>
                      <th className="py-1 pr-3 font-normal text-right">t2</th>
                      <th className="py-1 font-normal text-right">stopped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(outcomes.by_use_case ?? []).map((b) => (
                      <tr key={b.use_case} className="border-t border-hairline/40 text-muted">
                        <td className="py-1 pr-3 text-ink">{b.use_case}</td>
                        <td className="py-1 pr-3 text-right font-mono">{b.n}</td>
                        <td className={`py-1 pr-3 text-right font-mono ${(b.win_rate ?? 0) >= 0.5 ? 'text-aggressive' : 'text-defensive'}`}>
                          {b.win_rate != null ? `${Math.round(b.win_rate * 100)}%` : '—'}
                        </td>
                        <td className={`py-1 pr-3 text-right font-mono ${(b.avg_r ?? 0) >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                          {b.avg_r != null ? `${Number(b.avg_r).toFixed(2)}R` : '—'}
                        </td>
                        <td className="py-1 pr-3 text-right font-mono">
                          {b.t1_rate != null ? `${Math.round(b.t1_rate * 100)}%` : '—'}
                        </td>
                        <td className="py-1 pr-3 text-right font-mono">
                          {b.t2_rate != null ? `${Math.round(b.t2_rate * 100)}%` : '—'}
                        </td>
                        <td className="py-1 text-right font-mono">
                          {b.stop_rate != null ? `${Math.round(b.stop_rate * 100)}%` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="py-3 text-xs text-muted">
              no closed plans yet — the grader fills this in as you close
              trades; entry context + rules version are journaled on every
              open so outcomes attribute back to the spec that suggested them.
            </p>
          )}
          {closedPlans.length > 0 && (
            <div className="pt-2 divide-y divide-hairline/60">
              {closedPlans.slice(0, 8).map((p: PlanRow) => {
                const entry = Number(p.entry_px), stop = Number(p.stop_px),
                  close = Number(p.close_px)
                const sgn = p.direction === 'short' ? -1 : 1
                const r = (entry && stop && close && entry !== stop)
                  ? (close - entry) * sgn / Math.abs(entry - stop) : null
                return (
                  <div key={p.id} className="flex items-baseline justify-between gap-3 py-1.5 text-[11px]">
                    <span className="text-muted">
                      <Link href={`/stock?sym=${p.symbol}`} className="font-semibold text-ink hover:text-accent">{p.symbol}</Link>
                      <span className="text-faint"> {p.use_case} · in {money(entry)} → out {money(close)}</span>
                    </span>
                    <span className={`font-mono ${r != null && r >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                      {r != null ? `${r >= 0 ? '+' : ''}${r.toFixed(1)}R` : (p.close_reason ?? 'closed')}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </Gate>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — engine suggests levels, you place and manage the trade</span>
        <span className="font-mono">{plan?.as_of ?? ''}</span>
      </footer>
    </main>
  )
}
