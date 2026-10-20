import Link from 'next/link'
import { api, type PlanSuggestion, type PlanRow } from '@/lib/api'
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
  const [plan, open] = await Promise.all([
    api.incomePlan(funds),
    api.tradePlans(),
  ])
  const sectors = plan?.sectors ?? []
  const pos = plan?.posture ?? {}
  const noLongs = pos.new_longs === false
  const openPlans = open?.open ?? []
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
      </Gate>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — engine suggests levels, you place and manage the trade</span>
        <span className="font-mono">{plan?.as_of ?? ''}</span>
      </footer>
    </main>
  )
}
