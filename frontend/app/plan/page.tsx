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

function pct(v?: number | null) {
  return v != null ? `${(Number(v) * 100).toFixed(0)}%` : '—'
}

function StateDot({ v }: { v?: string | null }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${DOT[toneOf(v)]}`}
    />
  )
}

function Row({ s, funds }: { s: PlanSuggestion; funds?: number }) {
  const thesis = [
    s.instrument,
    s.strike ? `strike ${money(s.strike)}` : null,
    s.dte, s.iv_hv != null ? `iv/hv ${s.iv_hv}` : null,
    s.thesis ? `thesis ${s.thesis}` : null,
  ].filter(Boolean).join(' · ')
  return (
    <div className="border-t border-hairline/60 py-2.5 first:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            href={`/stock?sym=${s.symbol}`}
            className="font-semibold text-ink hover:text-accent"
          >
            {s.symbol}
          </Link>
          <span className="text-[10px] uppercase tracking-wider text-faint">
            {s.instrument}
          </span>
          <StateDot v={s.state ?? s.mom} />
          <span className="text-[11px] text-muted">
            {s.state ?? s.mom ?? ''}
            {s.dip_phase ? ` · ${s.dip_phase}` : ''}
          </span>
          {s.thesis && (
            <span className={`text-[11px] ${
              { ok: 'text-aggressive', warn: 'text-caution',
                bad: 'text-defensive', off: 'text-muted' }[
                toneOf(s.thesis)]
            }`}>
              thesis {String(s.thesis).replace(/_/g, ' ')}
              {s.thesis_dir === 'up' ? ' ▲' : s.thesis_dir === 'down' ? ' ▼' : ''}
            </span>
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
      {/* levels line */}
      <div className="pt-1 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-xs text-muted">
        {s.spot != null && <span>px {money(s.spot)}</span>}
        {s.strike != null && (
          <span className="text-ink">strike {money(s.strike)}</span>
        )}
        {s.entry_px != null && <span>entry {money(s.entry_px)}</span>}
        {s.stop_px != null && (
          <span className="text-defensive">stop {money(s.stop_px)}</span>
        )}
        {s.target_px != null && (
          <span className="text-aggressive">tgt {money(s.target_px)}</span>
        )}
        {s.rr != null && <span>R:R {Number(s.rr).toFixed(1)}</span>}
        {s.dte != null && <span>{s.dte}</span>}
        {s.iv_hv != null && (
          <span className={Number(s.iv_hv) >= 1 ? 'text-aggressive' : 'text-caution'}>
            iv/hv {s.iv_hv}
          </span>
        )}
        {s.collateral != null && (
          <span>collateral {money(s.collateral, 0)}</span>
        )}
        {s.contracts != null && s.contracts > 0 && (
          <span className="text-ink">
            {s.contracts} contract{s.contracts === 1 ? '' : 's'}
          </span>
        )}
        {s.shares != null && <span>{s.shares} sh held</span>}
        {s.score != null && <span className="text-faint">score {s.score}</span>}
        {s.rank != null && <span className="text-faint">rank {Number(s.rank).toFixed(0)}</span>}
        {s.earn_days != null && s.earn_days >= 0 && s.earn_days <= 35 && (
          <span className="text-caution">⚠ EPS {s.earn_days}d</span>
        )}
      </div>
      {(s.flags ?? []).map((f, i) => (
        <div key={i} className="pt-0.5 text-[11px] text-caution">⚠ {f}</div>
      ))}
      {(s.evidence ?? []).slice(0, 3).map((e, i) => (
        <div key={`e${i}`} className="pt-0.5 text-[11px] text-faint">· {e}</div>
      ))}
      {funds != null && s.use_case === 'csp' && s.contracts === 0 && (
        <div className="pt-0.5 text-[11px] text-faint">
          collateral {money(s.collateral, 0)} exceeds available funds
        </div>
      )}
    </div>
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
  const [plan, open] = await Promise.all([
    api.incomePlan(funds),
    api.tradePlans(),
  ])
  const lanes = plan?.lanes ?? {}
  const pos = plan?.posture ?? {}
  const noLongs = pos.new_longs === false
  const openPlans = open?.open ?? []
  const laneDefs: { key: keyof NonNullable<typeof lanes>; title: string; note: string }[] = [
    { key: 'swing', title: 'Swing calls', note: 'top engine picks — 5–20d holds' },
    { key: 'csp', title: 'Cash-secured puts', note: 'sell puts at support on sound names — premium or assignment at your price' },
    { key: 'covered_call', title: 'Covered calls', note: 'sell calls on held lots — income into strength' },
    { key: 'leap_call', title: 'LEAP calls', note: 'deep-ITM long-dated conviction' },
    { key: 'leap_put', title: 'LEAP puts', note: 'long-dated downside expressions' },
  ]
  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <header className="pt-6 pb-6">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Trading plan
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Today&apos;s <span className="text-accent">plan</span>
        </h1>
        <div className="pt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 ${
            noLongs ? 'text-defensive' : 'text-muted'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${noLongs ? 'bg-defensive' : 'bg-aggressive'}`} />
            posture {String(pos.posture ?? '—')}
            {pos.regime_as_of && (
              <span className="text-faint">· {String(pos.regime_as_of).slice(0, 10)}</span>
            )}
          </span>
          {noLongs && (
            <span className="text-defensive text-[11px]">
              new longs blocked — income/defense lanes only
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
        {plan?.note && (
          <p className="pt-2 max-w-xl text-xs text-faint">{plan.note}</p>
        )}
      </header>

      <Gate feature="board">
        {laneDefs.map(({ key, title, note }) => {
          const items = lanes[key] ?? []
          return (
            <section key={key} className="mt-4 rounded-xl border border-hairline bg-card px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] text-faint">{title}</span>
                <span className="text-[11px] text-faint">{note}</span>
              </div>
              <div className="pt-2">
                {items.length === 0 ? (
                  <p className="text-xs text-muted">
                    {noLongs && key !== 'covered_call' && key !== 'leap_put'
                      ? 'posture blocks new longs'
                      : 'nothing qualified today — no-trade is a valid plan'}
                  </p>
                ) : (
                  items.map((s) => <Row key={s.symbol + key} s={s} funds={funds} />)
                )}
              </div>
            </section>
          )
        })}

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
