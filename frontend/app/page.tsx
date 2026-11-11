import { api, type HorizonScenario, type RegimeVerdict } from '@/lib/api'
import { Chip, Kv, Section, Stat, fmtShort } from '@/components/regime'
import { VolChips } from '@/components/vol-chips'
import { TapeChips } from '@/components/tape-chips'
import { SessionTape } from '@/components/session-tape'
import { RetryRefresh } from '@/components/retry-refresh'

const TONE: Record<string, string> = {
  aggressive: 'text-aggressive',
  constructive: 'text-constructive',
  neutral: 'text-neutral',
  caution: 'text-caution',
  defensive: 'text-defensive',
}

const LABEL: Record<string, string> = {
  aggressive: 'Aggressive',
  constructive: 'Constructive',
  neutral: 'Neutral',
  caution: 'Caution',
  defensive: 'Defensive',
}

function fmtDate(d?: string) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return d
  }
}

function fmtDateTimeEt(d?: string) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
      timeZone: 'America/New_York',
    }) + ' ET'
  } catch {
    return d
  }
}

export default async function RegimePage() {
  const [posture, morning, tape, alarms, metals, fwd, irec] =
    await Promise.all([
      api.posture(),
      api.morningRegime(),
      api.intraday(),
      api.correctionAlarms(),
      api.metalsPulse(),
      api.forwardOutlook(),
      api.intradayRecovery(),
    ])

  const p = posture ?? {}
  const today = morning?.today
  const intraday = morning?.intraday
  const fragility = morning?.fragility
  const record = morning?.record ?? []

  const tone = TONE[p.posture ?? 'neutral'] ?? 'text-neutral'
  const label = LABEL[p.posture ?? 'neutral'] ?? 'Unknown'
  // today's morning snapshot is what this card renders — the posture
  // journal (regime_snapshots) refreshes overnight and can lag a day;
  // let the fresher read own the header date
  const asOf = today?.as_of || p.regime_as_of
  const latestUpdate = intraday?.market_time || tape?.ts || asOf

  const buckets =
    today?.buckets && typeof today.buckets === 'object' && !Array.isArray(today.buckets)
      ? (today.buckets as Record<string, unknown>)
      : null

  // structural layer — capex/macro/language journaled under buckets;
  // pull capex out for a real section instead of a JSON blob
  const structural =
    buckets && typeof buckets.structural === 'object' && buckets.structural !== null
      ? (buckets.structural as Record<string, unknown>)
      : null
  const capex =
    structural && typeof structural.capex === 'object' && structural.capex !== null
      ? (structural.capex as Record<string, unknown>)
      : null
  const fed =
    structural && typeof structural.fed === 'object' && structural.fed !== null
      ? (structural.fed as Record<string, unknown>)
      : null
  const liq =
    structural && typeof structural.liquidity === 'object' && structural.liquidity !== null
      ? (structural.liquidity as Record<string, unknown>)
      : null
  const liqComps = Array.isArray(liq?.components)
    ? (liq!.components as Record<string, unknown>[])
      .filter((c) => typeof c.score === 'number' && (c.weight as number) > 0)
    : []
  const liqImpulses = (liq?.impulses ?? {}) as Record<string, string>
  // green/yellow/red signal per component score — the spec's traffic
  // light: >=65 expanding (green), 45-64 neutral (yellow), <45
  // contracting (red)
  const liqDot = (s: number) =>
    s >= 65 ? 'bg-aggressive' : s >= 45 ? 'bg-caution' : 'bg-defensive'
  const liqChipTone = (v?: string) =>
    ['expanding', 'improving', 'accelerating', 'strong', 'inflows',
      'easing', 'releasing', 'adding'].includes(v ?? '')
      ? 'text-aggressive'
      : ['contracting', 'deteriorating', 'decelerating', 'weak',
        'outflows', 'tightening', 'absorbing', 'draining'].includes(v ?? '')
        ? 'text-defensive' : 'text-muted'
  const fedFomc =
    fed && typeof fed.next_fomc === 'object' && fed.next_fomc !== null
      ? (fed.next_fomc as Record<string, unknown>)
      : null
  const fed36 =
    fed && typeof fed.path_3_6m === 'object' && fed.path_3_6m !== null
      ? (fed.path_3_6m as Record<string, unknown>)
      : null
  const fedDq =
    fed && typeof fed.data_quality === 'object' && fed.data_quality !== null
      ? (fed.data_quality as Record<string, unknown>)
      : null

  // per-index technical cards — core US set + EFA/EEM overlay,
  // journaled under buckets.indexes by the regime engine
  const indexes =
    buckets && typeof buckets.indexes === 'object' && buckets.indexes !== null
      ? (buckets.indexes as Record<string, Record<string, unknown>>)
      : null
  const breadthBucket =
    buckets && typeof buckets.breadth === 'object' && buckets.breadth !== null
      ? (buckets.breadth as Record<string, unknown>)
      : null

  // evidence + cross-asset confirmation + macro instruments — all
  // journaled in buckets by the engine; surfaced below instead of
  // hiding inside the Kv dump
  const evidence =
    buckets && typeof buckets.evidence === 'object' && buckets.evidence !== null
      ? (buckets.evidence as Record<string, unknown>)
      : null
  const drivers = Array.isArray(evidence?.drivers)
    ? (evidence!.drivers as unknown[]).map(String)
    : []
  // market permissions — the mechanical gate (size multiplier,
  // breakout/dip restrictions) + deterministic notes explaining WHY
  // it tightened (independent families firing, deterioration, thin
  // coverage). Distinct from verdict.rules, which are label verbs.
  const permissions =
    evidence && typeof evidence.permissions === 'object' && evidence.permissions !== null
      ? (evidence.permissions as Record<string, unknown>)
      : null
  const permNotes = Array.isArray(permissions?.notes)
    ? (permissions!.notes as unknown[]).map(String)
    : []
  const confX =
    buckets && typeof buckets._confirmation === 'object' && buckets._confirmation !== null
      ? (buckets._confirmation as Record<string, unknown>)
      : null
  const confVotes =
    confX && typeof confX.votes === 'object' && confX.votes !== null
      ? (confX.votes as Record<string, string>)
      : null
  const macroDetail =
    buckets && typeof buckets.macro === 'object' && buckets.macro !== null &&
      typeof (buckets.macro as Record<string, unknown>).detail === 'object' &&
      (buckets.macro as Record<string, unknown>).detail !== null
      ? ((buckets.macro as Record<string, unknown>).detail as Record<string, { value?: number | null; chg5d?: number | null; delta5d?: number | null }>)
      : null
  // canonical engine read — the precise label + secondary regime the
  // 5-class display coarsens (e.g. 'bear' + 'macro_risk_off'); plus
  // the trajectory score the forward layer consumes
  const canonical =
    buckets && typeof buckets._canonical === 'object' && buckets._canonical !== null
      ? (buckets._canonical as Record<string, unknown>)
      : null
  // divergence safeguard — a bullish 5-class verdict got capped to
  // neutral because internals disagreed; silence would mislead
  const divergent = buckets?._divergent === true
  const canonicalLabel = canonical?.label
    ? `engine ${String(canonical.label).replace(/_/g, ' ')}${canonical.secondary ? ' · ' + String(canonical.secondary).replace(/_/g, ' ') : ''}`
    : null
  // slow structural macro regime — weeks-scale read from
  // macro_snapshots, distinct from the daily tape regime
  const structMacro =
    structural && typeof structural.macro === 'object' && structural.macro !== null
      ? (structural.macro as Record<string, unknown>)
      : null
  // forward — the ~20-session scenario distribution the regime engine
  // journals (forward_probs) + geo/defensive context. Bounded evidence,
  // not a forecast; the page shows the split, lead scenario, and the
  // drivers behind it
  const forward =
    buckets && typeof buckets.forward === 'object' && buckets.forward !== null
      ? (buckets.forward as Record<string, unknown>)
      : null
  const fwdNum = (k: string): number | null => {
    const v = forward?.[k]
    return typeof v === 'number' ? v : null
  }
  // geo context refreshes from the momentum job — a geo_as_of older
  // than ~36h means the read is stale, not current evidence
  const geoStale = typeof forward?.geo_as_of === 'string' &&
    Date.now() - new Date(forward.geo_as_of as string).getTime() >
    36 * 3600 * 1000

  const todayExtras = today
    ? Object.entries(today).filter(
      ([k]) =>
        !['as_of', 'regime', 'ai_regime', 'score', 'confidence',
          'buckets', 'verdict', 'horizon_1m', 'horizon_3m'].includes(k),
    )
    : []

  // horizons arrive as scenario objects ({base, bear, bull, stress,
  // windows, key_catalyst}) — sometimes empty {} when the LLM leg
  // didn't produce one; unwrap or drop
  const asHorizon = (v: unknown): HorizonScenario | null => {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const o = v as HorizonScenario
      return (o.base || o.bear || o.bull || o.stress ||
        o.key_catalyst || (o.windows?.length ?? 0) > 0) ? o : null
    }
    return null
  }
  const h1 = asHorizon(today?.horizon_1m)
  const h3 = asHorizon(today?.horizon_3m)

  // verdict is an object {plain, rules, confirmation, ...} — plain is
  // the human-readable call, rules are the action hints
  const verdict: RegimeVerdict | null =
    today?.verdict && typeof today.verdict === 'object'
      ? today.verdict as RegimeVerdict
      : null
  const renderVerdictCard = Boolean(
    verdict?.plain ||
    (verdict?.rules && Object.keys(verdict.rules).length > 0))

  // which feeds actually answered — a null means the section below
  // renders blank; name it instead of failing silently
  const missing = [
    posture ? null : 'posture',
    morning ? null : 'regime',
    tape ? null : 'tape',
    alarms ? null : 'alarms',
  ].filter(Boolean) as string[]

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="flex items-baseline justify-between pt-6 pb-8">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          See everything. Decide yourself.
        </span>
        <span className="font-mono text-xs text-faint">
          {latestUpdate ? `updated ${fmtDateTimeEt(latestUpdate)}` : '—'}
          {asOf && latestUpdate !== asOf && ` · baseline ${fmtDate(asOf)}`}
        </span>
      </header>

      {missing.length > 0 && (
        <div className="pb-6 flex items-center gap-2 text-xs text-caution">
          <span>
            live data unavailable ({missing.join(' · ')}) — retrying
            once automatically;
          </span>
          <RetryRefresh />
        </div>
      )}

      {/* hero — the one thing you read first */}
      <section className="pb-10">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Market regime
        </div>
        <h1 className={`pt-3 font-semibold text-display ${tone}`}>
          {label}
        </h1>
        {p.note && (
          <p className="pt-4 max-w-xl text-[15px] leading-relaxed text-muted">
            {p.note}
          </p>
        )}
        <div className="pt-6 flex flex-wrap gap-2">
          <Chip label={p.new_longs ? 'New longs' : 'No new longs'} on={!!p.new_longs} />
          <Chip label="Shorts" on={!!p.shorts} />
          {p.hedge_on && <Chip label="Hedge on" tone="warn" />}
          {p.matched && (
            <span className="inline-flex items-center rounded-full border border-hairline px-3 py-1 text-xs font-mono text-faint">
              {p.matched}
            </span>
          )}
        </div>
        <div className="pt-3">
          <VolChips vol={p.vol} bias={p.bias} />
        </div>
        <div className="pt-2">
          <TapeChips tape={tape} />
        </div>
        {alarms?.correction_character && (
          <div className="pt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
            <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
              alarms
            </span>
            <span className={`font-medium ${alarms.severity === 'alarm' ? 'text-defensive'
              : alarms.severity === 'warning' ? 'text-caution'
                : alarms.severity === 'watch' ? 'text-muted'
                  : 'text-faint'}`}>
              {alarms.correction_character.replace(/_/g, ' ')}
            </span>
            {alarms.legs?.labor_credit?.hy_oas != null && (
              <span className="font-mono text-muted" title={alarms.legs.labor_credit.note}>
                HY {alarms.legs.labor_credit.hy_oas}%
                {alarms.legs.labor_credit.hy_oas_d20 != null && ` ${alarms.legs.labor_credit.hy_oas_d20 > 0 ? '+' : ''}${alarms.legs.labor_credit.hy_oas_d20}`}
              </span>
            )}
            {alarms.legs?.real_yields?.dfii10 != null && (
              <span className="font-mono text-muted" title={alarms.legs.real_yields.note}>
                real10y {alarms.legs.real_yields.dfii10}%
                {alarms.legs.real_yields.dfii10_d20 != null && ` ${alarms.legs.real_yields.dfii10_d20 > 0 ? '+' : ''}${alarms.legs.real_yields.dfii10_d20}`}
              </span>
            )}
            {alarms.legs?.revision_breadth?.pct_cutting_5 != null && (
              <span className="font-mono text-muted" title={alarms.legs.revision_breadth.note}>
                est cuts {alarms.legs.revision_breadth.pct_cutting_5}%
              </span>
            )}
            {alarms.action?.bias && (
              <span className={`font-medium ${{
                sell: 'text-defensive',
                slow_buys: 'text-caution',
                hold: 'text-caution',
                accumulate_selective: 'text-accent',
                accumulate_staged: 'text-accent',
                accumulate: 'text-aggressive',
              }[alarms.action.bias] ?? 'text-muted'}`}
                title={alarms.action.note}>
                → {{
                  sell: 'start selling — raise cash',
                  slow_buys: 'slow the buys',
                  hold: 'hold / pause new buys',
                  accumulate_selective: 'accumulate selectively',
                  accumulate_staged: 'staged accumulation',
                  accumulate: 'accumulate',
                }[alarms.action.bias] ?? alarms.action.bias}
              </span>
            )}
            <span className="text-faint" title={alarms.meaning}>
              {alarms.meaning?.split('—')[0].trim()}
            </span>
          </div>
        )}
      </section>

      {/* session tape — how today unfolded: journaled 15-min states
          with the readings at each transition (the "gapped → rallied
          → faded — why" answer) */}
      {tape && <SessionTape tape={tape} />}

      {/* thin score strip */}
      {today && (
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-6 rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <Stat label="Regime" value={today.regime ?? '—'} />
          <Stat
            label="Score"
            value={today.score != null ? String(today.score) : '—'}
          />
          <Stat
            label="Confidence"
            value={
              today.confidence != null ? `${today.confidence}%` : '—'
            }
          />
          <Stat
            label="1M · 3M"
            value={`${h1?.base?.replace(/_/g, ' ') ?? '—'} · ${h3?.base?.replace(/_/g, ' ') ?? '—'}`}
          />
        </section>
      )}

      {/* hourly intraday overlay — timing read over the daily baseline */}
      {intraday && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Intraday update
            </div>
            <div className={`font-mono text-[11px] ${intraday.stale ? 'text-caution' : 'text-faint'}`}>
              {intraday.stale ? 'stale · ' : ''}
              {intraday.market_time
                ? new Date(intraday.market_time).toLocaleString('en-US', {
                    hour: 'numeric', minute: '2-digit',
                    timeZone: 'America/New_York',
                  }) + ' ET'
                : '—'}
            </div>
          </div>
          <div className="pt-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${intraday.tone === 'good'
              ? 'border-aggressive/40 text-aggressive'
              : intraday.tone === 'bad'
                ? 'border-defensive/40 text-defensive'
                : intraday.tone === 'warn'
                  ? 'border-caution/40 text-caution'
                  : 'border-hairline text-muted'}`}>
              {(intraday.state ?? '—').replace(/_/g, ' ')}
            </span>
            {intraday.tape_state && (
              <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                tape {intraday.tape_state.replace(/_/g, ' ')}
              </span>
            )}
            {intraday.baseline_regime && (
              <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                daily {intraday.baseline_regime.replace(/_/g, ' ')}
              </span>
            )}
            {/* forecast layer — direction vs conditions, separate
                reads: a clean trend-down can out-trade chop */}
            {typeof intraday.evidence?.prob_close_green === 'number' && (
              <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                green {Math.round((intraday.evidence.prob_close_green as number) * 100)}%
              </span>
            )}
            {typeof intraday.evidence?.tradeability === 'number' && (
              <span className={`rounded-full border px-3 py-1 font-mono text-[11px] ${
                (intraday.evidence.tradeability as number) >= 65
                  ? 'border-aggressive/40 text-aggressive'
                  : (intraday.evidence.tradeability as number) >= 45
                    ? 'border-hairline text-muted'
                    : 'border-defensive/40 text-defensive'}`}>
                tradeable {(intraday.evidence.tradeability as number)}
                {intraday.evidence.tradeability_cls
                  ? ` · ${String(intraday.evidence.tradeability_cls).replace(/_/g, ' ')}`
                  : ''}
              </span>
            )}
            {(() => {
              const dt = intraday.evidence?.day_type as
                | Record<string, number> | undefined
              if (!dt) return null
              const top = Object.entries(dt)
                .sort((a, b) => b[1] - a[1])[0]
              return top ? (
                <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                  {top[0].replace('p_', '').replace(/_/g, ' ')} {Math.round(top[1] * 100)}%
                </span>
              ) : null
            })()}
          </div>
          {intraday.action && (
            <p className="pt-3 text-sm leading-relaxed text-ink">
              {intraday.action}
            </p>
          )}
          {Array.isArray(intraday.evidence?.tape) &&
            (intraday.evidence!.tape as unknown[]).length > 0 && (
              <div className="pt-2 space-y-0.5">
                {(intraday.evidence!.tape as unknown[]).slice(0, 3).map((e, i) => (
                  <p key={i} className="text-[11px] leading-relaxed text-muted">
                    · {String(e)}
                  </p>
                ))}
              </div>
            )}
        </section>
      )}

      {/* ai-infra intraday recovery — who's holding vwap with real
          buying vs relief rally vs failing. 5-min engine, journaled
          each bar; % gain is never the signal. */}
      {(irec?.symbols?.length ?? 0) > 0 && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2 pb-2">
            <h2 className="text-sm font-semibold tracking-wide text-ink">
              AI-infra recovery — vwap confirmation
            </h2>
            <div className="font-mono text-[11px] text-faint">
              {irec!.as_of
                ? new Date(irec!.as_of).toLocaleTimeString('en-US', {
                    hour: 'numeric', minute: '2-digit',
                    timeZone: 'America/New_York' }) + ' ET'
                : ''}
              {irec!.stale ? ' · stale' : ''}
              {irec!.participation != null &&
                ` · ${Math.round(irec!.participation)}% of universe above vwap`}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <tbody>
                {irec!.symbols!.slice(0, 20).map((r) => {
                  const sig = r.signal ?? 'WATCH'
                  const cls =
                    sig === 'STRONG_RECOVERY' ? 'text-aggressive'
                    : sig === 'CONFIRMED_RECOVERY' ? 'text-aggressive/80'
                    : sig === 'IMPROVING' ? 'text-caution'
                    : sig === 'DISTRIBUTION' || sig === 'FAILED_REBOUND'
                      ? 'text-defensive'
                    : 'text-faint'
                  return (
                    <tr key={r.symbol} className="border-t border-hairline/40">
                      <td className="py-1 pr-3 font-medium">
                        <a href={`/stock?symbol=${r.symbol}`}>{r.symbol}</a>
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
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* systematic fragility — leverage/positioning under the tape.
          orthogonal to regime: bullish tape can still be loaded */}
      {fragility?.vulnerability != null && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Systematic fragility — selling early warning
            </div>
            <div className="font-mono text-[11px] text-faint">
              {fragility.as_of} · conf {fragility.confidence}
              {fragility.coverage_pct != null &&
                ` · ${Math.round(fragility.coverage_pct)}% observed`}
            </div>
          </div>
          <div className="pt-3 flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-3 py-1 text-xs font-medium ${
              (fragility.band ?? '') === 'critical' || (fragility.band ?? '') === 'fragile'
                ? 'border-defensive/40 text-defensive'
                : (fragility.band ?? '') === 'elevated'
                  ? 'border-caution/40 text-caution'
                  : 'border-aggressive/40 text-aggressive'}`}>
              {Math.round(fragility.vulnerability)} — {(fragility.band ?? '—').replace(/_/g, ' ')}
            </span>
            {fragility.selling_pressure?.score != null && (
              <span className={`rounded-full border px-3 py-1 font-mono text-[11px] ${
                (fragility.selling_pressure.score ?? 0) >= 45
                  ? 'border-defensive/40 text-defensive'
                  : (fragility.selling_pressure.score ?? 0) >= 20
                    ? 'border-caution/40 text-caution'
                    : 'border-hairline text-muted'}`}>
                selling {Math.round(fragility.selling_pressure.score)}
              </span>
            )}
            {fragility.exhaustion?.score != null && (
              <span className={`rounded-full border px-3 py-1 font-mono text-[11px] ${
                (fragility.exhaustion.score ?? 0) >= 50
                  ? 'border-aggressive/40 text-aggressive'
                  : (fragility.exhaustion.score ?? 0) >= 30
                    ? 'border-caution/40 text-caution'
                    : 'border-hairline text-muted'}`}>
                exhaustion {Math.round(fragility.exhaustion.score)} · {fragility.exhaustion.band}
              </span>
            )}
            {(['continuation', 'exhaustion', 'onset'] as const).map((fam) => {
              const p = fragility.probabilities?.[fam]?.['5d']
              if (p == null) return null
              return (
                <span key={fam}
                  className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                  {fam === 'continuation' ? 'cont' : fam === 'exhaustion' ? 'exh' : 'onset'} 5d {(p * 100).toFixed(0)}%
                </span>
              )
            })}
          </div>
          {fragility.read && (
            <p className="pt-3 text-sm leading-relaxed text-ink">
              {fragility.read}
            </p>
          )}
          {fragility.resolution?.phase && (
            <div className="pt-3 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
                cycle
              </span>
              <span className={`rounded-full border px-3 py-1 text-xs font-medium ${
                fragility.resolution.phase === 'recovering' || fragility.resolution.phase === 'quiet'
                  ? 'border-aggressive/40 text-aggressive'
                  : fragility.resolution.phase === 'stabilizing'
                    ? 'border-caution/40 text-caution'
                    : 'border-defensive/40 text-defensive'}`}>
                {fragility.resolution.phase}
              </span>
              {fragility.resolution.discharge_score != null && (
                <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                  discharge {Math.round(fragility.resolution.discharge_score)}
                </span>
              )}
              {fragility.resolution.bottom_score != null && (
                <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
                  bottoming {Math.round(fragility.resolution.bottom_score)}
                </span>
              )}
            </div>
          )}
          {fragility.resolution?.read && (
            <p className="pt-1 text-[12px] leading-relaxed text-muted">
              {fragility.resolution.read}
            </p>
          )}
          <div className="pt-3 space-y-1">
            {Object.entries(fragility.legs ?? {}).map(([name, leg]) => (
              <div key={name} className="flex items-baseline gap-2 text-[11px] leading-relaxed">
                <span className="w-32 shrink-0 font-mono text-faint">
                  {name.replace(/_/g, ' ')}
                </span>
                <span className={`w-8 shrink-0 font-mono ${
                  (leg.score ?? 0) >= 70 ? 'text-defensive'
                  : (leg.score ?? 0) >= 45 ? 'text-caution' : 'text-muted'}`}>
                  {leg.score != null ? Math.round(leg.score) : '—'}
                </span>
                <span className={`shrink-0 font-mono ${
                  leg.status === 'observed' ? 'text-faint'
                  : leg.status === 'estimated' ? 'text-caution' : 'text-faint'}`}>
                  {leg.status === 'observed' ? 'obs' : leg.status === 'estimated' ? 'est' : '—'}
                </span>
                <span className="text-muted">{leg.read}</span>
              </div>
            ))}
          </div>
          {Array.isArray(fragility.firing) &&
            fragility.firing.length > 0 && (
              <p className="pt-2 font-mono text-[11px] text-defensive">
                firing: {(fragility.firing as string[]).map((f) => f.replace(/_/g, ' ')).join(' · ')}
              </p>
            )}
        </section>
      )}

      {/* verdict — the plain-English call + action rules */}
      {renderVerdictCard && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Today's call
          </div>
          {verdict?.plain && (
            <p className="pt-3 text-sm leading-relaxed text-ink">
              {verdict.plain}
            </p>
          )}
          {verdict?.rules && Object.keys(verdict.rules).length > 0 && (
            <div className="pt-3 flex flex-wrap gap-2">
              {Object.entries(verdict.rules)
                .filter(([k]) => k !== 'note')
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="rounded-full border border-hairline px-3 py-1 text-xs text-muted"
                  >
                    {k.replace(/_/g, ' ')}{' '}
                    <span className="font-medium text-ink">
                      {String(v).replace(/_/g, ' ')}
                    </span>
                  </span>
                ))}
            </div>
          )}
          {verdict?.rules?.note && (
            <p className="pt-2 text-[11px] text-faint">
              {verdict.rules.note}
            </p>
          )}

          {/* regime meta — event risk, data quality, lean, changes */}
          {Boolean(verdict?.event_risk || verdict?.data_quality || verdict?.qqq_lean ||
            today?.ai_regime || verdict?.llm_dissent || canonicalLabel ||
            divergent) && (
              <div className="pt-3 flex flex-wrap gap-2">
                {!!verdict?.event_risk && (
                  <Chip label={`event risk ${String(verdict.event_risk)}`}
                    tone={verdict.event_risk === 'extreme' || verdict.event_risk === 'high' ? 'warn' : 'off'} />
                )}
                {!!verdict?.data_quality && (
                  <Chip label={`data ${String(verdict.data_quality)}`} tone="off" />
                )}
                {today?.ai_regime && (
                  <Chip label={`ai growth ${today.ai_regime.replace(/_/g, ' ')}`} tone="off" />
                )}
                {!!verdict?.qqq_lean && (
                  <Chip label={`qqq lean ${String(verdict.qqq_lean).replace(/_/g, ' ')}`} tone="off" />
                )}
                {!!verdict?.llm_dissent && (
                  <Chip label="llm dissent" tone="warn" />
                )}
                {!!canonicalLabel && (
                  <Chip label={canonicalLabel} tone="off" />
                )}
                {divergent && (
                  <Chip label="capped — internals disagree" tone="warn" />
                )}
                {typeof canonical?.deterioration_score === 'number' && (
                  <Chip
                    label={`deterioration ${(canonical.deterioration_score as number) >= 0 ? '+' : ''}${(canonical.deterioration_score as number).toFixed(2)}`}
                    tone={(canonical.deterioration_score as number) < -0.3 ? 'warn' : 'off'} />
                )}
              </div>
            )}

          {/* posture — the mechanical permission gate. Restrictions
              show only when active; the notes say WHY it tightened
              (independent families firing, deterioration slope, thin
              evidence) — not the label verbs in verdict.rules */}
          {permissions && (
            <div className="pt-3 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                  posture
                </span>
                {typeof permissions.size_multiplier === 'number' && (
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-mono ${Number(permissions.size_multiplier) < 1
                      ? 'border-caution/40 text-caution'
                      : 'border-hairline text-muted'
                      }`}
                  >
                    size ×{Number(permissions.size_multiplier).toFixed(2)}
                  </span>
                )}
                {permissions.breakout_buying != null &&
                  permissions.breakout_buying !== 'allowed' && (
                    <span className="rounded-full border border-caution/40 px-2.5 py-0.5 text-[11px] font-mono text-caution">
                      breakouts {String(permissions.breakout_buying)}
                    </span>
                  )}
                {permissions.dip_buying === false && (
                  <span className="rounded-full border border-defensive/40 px-2.5 py-0.5 text-[11px] font-mono text-defensive">
                    dip-buying off
                  </span>
                )}
                {permissions.aggressive_long === false && (
                  <span className="rounded-full border border-hairline px-2.5 py-0.5 text-[11px] font-mono text-muted">
                    no aggressive adds
                  </span>
                )}
              </div>
              {permNotes.map((n, i) => (
                <p key={i} className="text-[11px] leading-relaxed text-muted">
                  · {n}
                </p>
              ))}
            </div>
          )}

          {/* cross-asset confirmation — do other markets underwrite
              the equity move? journaled votes per asset */}
          {confVotes && Object.keys(confVotes).length > 0 && (
            <div className="pt-3 flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                x-asset
              </span>
              {Object.entries(confVotes).map(([k, v]) => (
                <span
                  key={k}
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-mono ${v === 'confirm'
                    ? 'border-aggressive/40 text-aggressive'
                    : 'border-defensive/40 text-defensive'
                    }`}
                >
                  {k.replace(/_/g, ' ')} {v === 'confirm' ? '✓' : '✗'}
                </span>
              ))}
              {!!confX?.label && (
                <span className="text-[11px] text-faint">
                  {String(confX.label)}
                </span>
              )}
            </div>
          )}

          {/* what changed — deterministic day-over-day dimension diffs */}
          {Array.isArray(verdict?.changes) && (verdict!.changes as unknown[]).length > 0 && (
            <div className="pt-3 space-y-0.5">
              {(verdict!.changes as unknown[]).slice(0, 4).map((c, i) => (
                <p key={i} className="text-[11px] leading-relaxed text-muted">
                  Δ {typeof c === 'string' ? c : JSON.stringify(c)}
                </p>
              ))}
            </div>
          )}
        </section>
      )}

      {/* what's driving it — the deterministic driver lines (index
          composite, breadth divergence, SMA breaks) as bullets, not
          a JSON blob */}
      {drivers.length > 0 && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            What&apos;s driving it
          </div>
          <div className="pt-3 space-y-1">
            {drivers.slice(0, 8).map((d, i) => (
              <p key={i} className="text-[12px] leading-relaxed text-muted">
                · {d}
              </p>
            ))}
          </div>
        </section>
      )}

      {/* forward — the ~20-session scenario split the engine journals:
          deeper / chop / resolves-bullish, plus the geo + defensive
          context feeding it. Bounded evidence-weighted estimate, not
          a forecast — calibration happens against realized outcomes */}
      {forward && fwdNum('p_deeper_dip_20d') !== null && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Next ~20 sessions
            </div>
            {typeof forward.lead_scenario === 'string' && (
              <span className="font-mono text-[11px] text-faint">
                lead · {String(forward.lead_scenario).replace(/_/g, ' ')}
                {forward.confidence === 'low' ? ' · low conf'
                  : forward.confidence === 'medium' ? ' · med conf' : ''}
              </span>
            )}
          </div>
          <div className="pt-3">
            <div className="flex h-2 w-full overflow-hidden rounded-full">
              <div className="bg-defensive"
                style={{ width: `${fwdNum('p_deeper_dip_20d')}%` }} />
              <div className="bg-neutral"
                style={{ width: `${fwdNum('p_chop_20d')}%` }} />
              <div className="bg-aggressive"
                style={{ width: `${fwdNum('p_bullish_20d')}%` }} />
            </div>
            <div className="pt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px]">
              <span className="text-defensive">
                ↓ deeper {fwdNum('p_deeper_dip_20d')}%
              </span>
              <span className="text-muted">
                ↔ chop {fwdNum('p_chop_20d')}%
              </span>
              <span className="text-aggressive">
                ↑ growth {fwdNum('p_bullish_20d')}%
              </span>
            </div>
          </div>
          {(fwdNum('geo_risk') !== null ||
            typeof forward.defensive_stage === 'string' ||
            typeof forward.defensive_flow === 'string' ||
            geoStale) && (
              <div className="pt-3 flex flex-wrap gap-1.5">
                {fwdNum('geo_risk') !== null && fwdNum('geo_risk')! > 0 && (
                  <span className={`rounded-full px-2.5 py-1 text-[11px] ${(fwdNum('geo_risk') ?? 0) >= 50 ? 'bg-defensive/10 text-defensive' : 'bg-elevated text-muted'}`}>
                    geo-risk {fwdNum('geo_risk')}/100
                  </span>
                )}
                {geoStale && (
                  <span className="rounded-full bg-caution/10 px-2.5 py-1 text-[11px] text-caution">
                    geo data stale
                  </span>
                )}
                {typeof forward.defensive_stage === 'string' &&
                  forward.defensive_stage !== 'NORMAL' && (
                    <span className="rounded-full bg-defensive/10 px-2.5 py-1 text-[11px] text-defensive">
                      defensive · {String(forward.defensive_stage).replace(/_/g, ' ').toLowerCase()}
                      {fwdNum('defensive_score') !== null && ` ${fwdNum('defensive_score')}`}
                    </span>
                  )}
                {forward.defensive_flow === 'risk-off' && (
                  <span className="rounded-full bg-elevated px-2.5 py-1 text-[11px] text-muted">
                    flows risk-off
                  </span>
                )}
              </div>
            )}
          {Array.isArray(forward.geo_drivers) && forward.geo_drivers.length > 0 && (
            <div className="pt-2 space-y-0.5">
              <div className="text-[10px] uppercase tracking-[0.18em] text-faint">
                headline risk
              </div>
              {(forward.geo_drivers as unknown[]).slice(0, 3).map((d, i) => (
                <p key={i} className="text-[11px] leading-relaxed text-muted">
                  · {String(d)}
                </p>
              ))}
            </div>
          )}
          {Array.isArray(forward.drivers) && forward.drivers.length > 0 && (
            <div className="pt-2.5 space-y-0.5">
              {(forward.drivers as unknown[]).slice(0, 5).map((d, i) => (
                <p key={i} className="text-[11px] leading-relaxed text-muted">
                  · {String(d)}
                </p>
              ))}
            </div>
          )}
          <p className="pt-2 text-[10px] text-faint">
            evidence-weighted scenario split — calibrates against
            realized outcomes as journal history accrues
          </p>
        </section>
      )}

      {/* outlook — 1M/3M scenario windows with catalysts */}
      {(h1 || h3) && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Outlook
          </div>
          <div className="pt-4 grid gap-5 sm:grid-cols-2">
            {([['Next month', h1], ['Next quarter', h3]] as const).map(
              ([label, h]) => h && (
                <div key={label}>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-medium text-muted">{label}</span>
                    {h.base && (
                      <span className="text-sm font-semibold text-ink">
                        {h.base.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  {(h.bull || h.bear || h.stress) && (
                    <div className="pt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted">
                      {h.bull && <span>↑ {h.bull.replace(/_/g, ' ')}</span>}
                      {h.bear && <span>↓ {h.bear.replace(/_/g, ' ')}</span>}
                      {h.stress && (
                        <span className="text-defensive">⚡ {h.stress.replace(/_/g, ' ')}</span>
                      )}
                    </div>
                  )}
                  {h.key_catalyst && (
                    <p className="pt-1.5 text-[11px] leading-relaxed text-muted">
                      catalyst · {h.key_catalyst}
                    </p>
                  )}
                  {h.windows && h.windows.length > 0 && (
                    <p className="pt-1 text-[11px] text-faint">
                      {h.windows.join(' → ')}
                    </p>
                  )}
                </div>
              ),
            )}
          </div>
        </section>
      )}

      {/* structural macro — the slow weeks-scale regime read from
          macro_snapshots (inflation/growth/liquidity modules → regime
          probs). Distinct horizon from the daily tape regime above */}
      {structMacro && Boolean(typeof structMacro.overall === 'number' ||
        (structMacro.regime_probs != null &&
          typeof structMacro.regime_probs === 'object' &&
          Object.keys(structMacro.regime_probs as object).length > 0)) && (
          <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
            <div className="flex items-baseline justify-between">
              <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
                Structural macro
              </div>
              {structMacro.age_days != null && (
                <span className={`font-mono text-[11px] ${typeof structMacro.age_days === 'number' && structMacro.age_days > 7 ? 'text-caution' : 'text-faint'}`}>
                  {String(structMacro.age_days)}d old
                </span>
              )}
            </div>
            <div className="pt-3 flex items-baseline gap-6">
              {typeof structMacro.overall === 'number' && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-faint">
                    composite
                  </div>
                  <div className="font-mono text-lg text-ink">
                    {structMacro.overall.toFixed(0)}
                  </div>
                </div>
              )}
              {Boolean(structMacro.regime_probs &&
                typeof structMacro.regime_probs === 'object') && (
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    {Object.entries(structMacro.regime_probs as Record<string, unknown>)
                      .filter(([, v]) => typeof v === 'number')
                      .sort((a, b) => (b[1] as number) - (a[1] as number))
                      .slice(0, 3)
                      .map(([k, v]) => (
                        <span key={k} className="font-mono text-[11px] text-muted">
                          {k.replace(/_/g, ' ')} {(v as number) <= 1
                            ? Math.round((v as number) * 100)
                            : Math.round(v as number)}%
                        </span>
                      ))}
                  </div>
                )}
            </div>
          </section>
        )}

      {/* Liquidity & new-money flow — the transmission chain: Fed BS →
          TGA/RRP/reserves → credit → equity participation. Answers 'how
          aggressive can we be', never 'what to buy'. Traffic-light dots
          per component: green expanding / yellow neutral / red
          contracting. */}
      {liq && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Liquidity &amp; flows
            </div>
            <span className="font-mono text-[11px] text-faint">
              {liq.age_days != null && `snap ${String(liq.age_days)}d`}
              {(() => {
                const dw = liq.data_window as Record<string, unknown> | undefined
                return typeof dw?.oldest_age_days === 'number' &&
                  (dw.oldest_age_days as number) > 0
                  ? ` · oldest obs ${dw.oldest_age_days}d`
                  : ''
              })()}
              {typeof liq.coverage === 'number' &&
                ` · ${Math.round((liq.coverage as number) * 100)}% feeds`}
            </span>
          </div>
          <div className="pt-4 flex items-baseline gap-6">
            {typeof liq.liquidity_score === 'number' && (
              <div>
                <div className={`font-mono text-2xl font-semibold ${(liq.liquidity_score as number) >= 65
                  ? 'text-aggressive'
                  : (liq.liquidity_score as number) >= 45
                    ? 'text-caution' : 'text-defensive'}`}>
                  {String(liq.liquidity_score)}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-faint">
                  impulse / 100
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
              {liq.band != null && (
                <span className="font-mono text-ink">
                  {String(liq.band).replace(/_/g, ' ')}
                </span>
              )}
              {liq.liquidity_direction != null && (
                <span>
                  <span className="text-faint">direction </span>
                  <span className={liqChipTone(String(liq.liquidity_direction))}>
                    {String(liq.liquidity_direction)}
                  </span>
                </span>
              )}
              {liq.liquidity_acceleration != null && (
                <span>
                  <span className="text-faint">accel </span>
                  <span className={liqChipTone(String(liq.liquidity_acceleration))}>
                    {String(liq.liquidity_acceleration)}
                  </span>
                </span>
              )}
              {liq.equity_transmission != null && (
                <span>
                  <span className="text-faint">→ equities </span>
                  <span className={liqChipTone(String(liq.equity_transmission))}>
                    {String(liq.equity_transmission)}
                  </span>
                </span>
              )}
            </div>
          </div>
          {/* component traffic lights */}
          {liqComps.length > 0 && (
            <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2">
              {liqComps.map((c) => (
                <div key={String(c.name)} className="flex items-baseline gap-1.5"
                  title={[c.series, c.note, c.obs ? `obs ${c.obs}` : null]
                    .filter(Boolean).join(' · ') || undefined}>
                  <span className={`h-2 w-2 shrink-0 rounded-full ${liqDot(Number(c.score))}`} />
                  <span className="text-[11px] text-muted">
                    {String(c.name).replace(/_/g, ' ')}
                    {c.note != null &&
                      <span className="text-faint"> · {String(c.note)}</span>}
                  </span>
                  <span className="ml-auto font-mono text-[11px] text-ink">
                    {String(c.score)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {/* impulses — the labeled state per leg */}
          {Object.keys(liqImpulses).length > 0 && (
            <div className="pt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
              {Object.entries(liqImpulses).map(([k, v]) => (
                <span key={k}>
                  <span className="text-faint">{k.replace(/_/g, ' ')} </span>
                  <span className={liqChipTone(v)}>{String(v)}</span>
                </span>
              ))}
            </div>
          )}
          {/* M2 — context only, deliberately unscored: broad money
              isn't money allocated to equities */}
          {typeof (liq.context as Record<string, unknown> | undefined)
            ?.m2_yoy === 'number' && (
              <p className="pt-2 text-[10px] text-faint">
                M2 {((liq.context as Record<string, unknown>).m2_yoy as number) > 0 ? '+' : ''}
                {String((liq.context as Record<string, unknown>).m2_yoy)}% yoy
                {(liq.context as Record<string, unknown>).m2_obs != null &&
                  ` (${String((liq.context as Record<string, unknown>).m2_obs)})`}
                {' '}· broad money, context — not a scored leg
              </p>
            )}
          <p className="pt-2 text-[10px] text-faint">
            weekly · Fed BS/TGA/RRP/reserves + credit + breadth/semi-strength proxy
            — supports or caps aggressiveness, never selects names
          </p>
        </section>
      )}

      {/* AI capex cycle — the structural leg under the tape regime:
          hyperscaler spend decel → orders → TSM → ASML chain, scored
          0-100 (higher = slowdown). Sits next to the score strip. */}
      {capex && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              AI capex cycle
            </div>
            {capex.age_days != null && (
              <span className="font-mono text-[11px] text-faint">
                {String(capex.age_days)}d old
              </span>
            )}
          </div>
          <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-6">
            <Stat label="Band" value={String(capex.band ?? '—')} />
            <Stat
              label="Score"
              value={capex.score != null ? String(capex.score) : '—'}
            />
            <Stat
              label="Δ 3m"
              value={
                capex.d3m != null
                  ? `${Number(capex.d3m) >= 0 ? '+' : ''}${String(capex.d3m)}`
                  : '—'
              }
            />
            <Stat
              label="Legs elevated"
              value={
                capex.n_elevated != null
                  ? `${String(capex.n_elevated)} / 8`
                  : '—'
              }
            />
          </div>
          {Array.isArray(capex.flags) && capex.flags.length > 0 && (
            <div className="pt-4 flex flex-wrap gap-2">
              {(capex.flags as unknown[]).map((f) => (
                <Chip key={String(f)} label={String(f)} tone="warn" />
              ))}
            </div>
          )}
          {capex.guidance != null && (
            <p className="pt-3 text-xs leading-relaxed text-muted">
              {String(capex.guidance)}
            </p>
          )}
        </section>
      )}

      {/* Fed path — hike/hold/cut odds for the next FOMC + the 3-6m
          rate lean. Deterministic: market baseline (IRX pricing) +
          bounded econ-pressure shift. Journal-graded like everything
          else — confidence is earned, never declared. */}
      {fed && fedFomc && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Fed path
            </div>
            <span className="font-mono text-[11px] text-faint">
              {fedDq?.confidence ? `${String(fedDq.confidence)} conf` : ''}
              {fed.age_days != null && ` · ${String(fed.age_days)}d old`}
            </span>
          </div>

          {/* today's conclusion — one deterministic paragraph */}
          {fed.conclusion != null && (
            <p className="pt-3 text-sm leading-relaxed text-ink">
              {String(fed.conclusion)}
            </p>
          )}

          {/* probability bar — hike / hold / cut */}
          <div className="pt-4">
            <div className="flex justify-between text-[11px] text-faint pb-1.5">
              <span>
                next FOMC{fedFomc.date ? ` · ${String(fedFomc.date)}` : ''}
                {fedFomc.days_away != null && ` (${String(fedFomc.days_away)}d)`}
              </span>
              <span>
                {fedFomc.expected_bps != null &&
                  `${Number(fedFomc.expected_bps) > 0 ? '+' : ''}${String(fedFomc.expected_bps)}bp expected`}
              </span>
            </div>
            <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-hairline/60">
              {Number(fedFomc.p_hike) > 0 && (
                <div className="bg-defensive" style={{ width: `${Number(fedFomc.p_hike)}%` }} />
              )}
              {Number(fedFomc.p_hold) > 0 && (
                <div className="bg-neutral" style={{ width: `${Number(fedFomc.p_hold)}%` }} />
              )}
              {Number(fedFomc.p_cut) > 0 && (
                <div className="bg-aggressive" style={{ width: `${Number(fedFomc.p_cut)}%` }} />
              )}
            </div>
            <div className="pt-1.5 flex gap-4 font-mono text-[11px]">
              <span className="text-defensive">hike {String(fedFomc.p_hike ?? 0)}%</span>
              <span className="text-neutral">hold {String(fedFomc.p_hold ?? 0)}%</span>
              <span className="text-aggressive">cut {String(fedFomc.p_cut ?? 0)}%</span>
            </div>
          </div>

          <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-6">
            <Stat
              label="Policy rate"
              value={fed.policy_rate != null ? `${Number(fed.policy_rate).toFixed(2)}%` : '—'}
            />
            <Stat
              label="This month"
              value={
                fed.path_1m && typeof fed.path_1m === 'object'
                  ? String((fed.path_1m as Record<string, unknown>).lean ?? '—')
                  : '—'
              }
            />
            <Stat
              label="3-6m lean"
              value={fed36?.lean ? String(fed36.lean).replace(/_/g, ' ') : '—'}
            />
            <Stat
              label="3-6m implied"
              value={
                fed36?.expected_bps != null
                  ? `${Number(fed36.expected_bps) > 0 ? '+' : ''}${String(fed36.expected_bps)}bp`
                  : '—'
              }
            />
          </div>

          {Array.isArray(fed.drivers) && fed.drivers.length > 0 && (
            <div className="pt-3 space-y-0.5">
              {(fed.drivers as unknown[]).slice(0, 5).map((d, i) => (
                <p key={i} className="text-[11px] leading-relaxed text-muted">
                  · {String(d)}
                </p>
              ))}
            </div>
          )}
        </section>
      )}

      {/* index technicals — the core US set + global overlay, visible:
          the composite read the drivers cite lives here, not in a
          collapsed dump */}
      {indexes && Object.keys(indexes).length > 0 && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="flex items-baseline justify-between">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Index technicals
            </div>
            <span className="font-mono text-[11px] text-faint">
              {breadthBucket?.divergence != null
                ? `large-cap ${breadthBucket.large_cap ?? '—'}% vs broad ${breadthBucket.broad ?? '—'}% above 50d`
                : 'core US set + global overlay'}
            </span>
          </div>
          <div className="pt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {Object.entries(indexes).map(([sym, ix]) => {
              const num = (k: string) =>
                typeof ix?.[k] === 'number' ? (ix[k] as number) : null
              const rsi = num('rsi14')
              const overlay = ix?.overlay === true
              const NAME: Record<string, string> = {
                SPY: 'S&P 500', QQQ: 'Nasdaq 100', DIA: 'Dow 30',
                IWM: 'Russell 2000', MDY: 'Mid-caps', RSP: 'S&P equal-wt',
                EFA: 'Developed ex-US', EEM: 'Emerging mkts',
                SMH: 'AI infra / semis',
              }
              // deterministic trend read — the same inputs the card
              // shows, turned into one honest sentence
              const a200 = ix?.above_sma200 === true
              const a50 = ix?.above_sma50 === true
              const a20 = ix?.above_sma20 === true
              const trend =
                a200 && a50 && a20
                  ? (rsi != null && rsi >= 70
                      ? "uptrend — overbought, don't chase"
                      : 'uptrend intact — pullbacks are buys')
                : a200 && a50
                  ? 'uptrend, short-term dip — watch 20d'
                : a200 && !a50
                  ? (rsi != null && rsi <= 35
                      ? 'pullback in uptrend — oversold, watch for base'
                      : 'pullback in uptrend — below 50d, wait')
                : !a200 && a50
                  ? "repair rally under 200d — unconfirmed, don't chase"
                : !a200 && !a50
                  ? (rsi != null && rsi <= 30
                      ? 'downtrend, deeply oversold — no knife-catch'
                      : 'downtrend — rallies are sells until 50d')
                  : 'mixed — no clear trend'
              return (
                <div
                  key={sym}
                  className="rounded-md border border-hairline/60 px-3 py-2"
                >
                  <div className="flex items-baseline justify-between">
                    <span className="text-[13px] font-semibold">
                      {sym}
                      <span className="ml-1 font-normal text-[10px] text-faint">
                        {NAME[sym] ?? ''}
                      </span>
                    </span>
                    <span className="font-mono text-[11px] text-faint">
                      {overlay ? 'overlay' : rsi != null ? `RSI ${rsi.toFixed(0)}` : ''}
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-[12px] text-muted">
                    {num('price')?.toFixed(2) ?? '—'}
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted">{trend}</div>
                  <div className="mt-1 space-y-0.5 font-mono text-[11px]">
                    {(['sma20', 'sma50', 'sma200'] as const).map((ma) => {
                      const above = ix?.[`above_${ma}`]
                      const dist = num(`dist_${ma}`)
                      const days = ma === 'sma50' ? num('days_below_sma50') : null
                      return (
                        <div key={ma} className="flex justify-between">
                          <span className="text-faint">
                            {ma.replace('sma', '')}d
                          </span>
                          <span
                            className={
                              above === true
                                ? 'text-constructive'
                                : above === false
                                  ? 'text-defensive'
                                  : 'text-faint'
                            }
                          >
                            {dist != null
                              ? `${dist >= 0 ? '+' : ''}${(dist * 100).toFixed(1)}%`
                              : '—'}
                            {days != null && days > 0 ? ` ·${days}d` : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* cross-asset instruments — 10Y/DXY/credit/TLT/gold/oil with
          5d moves; the raw evidence the confirmation votes cite */}
      {macroDetail && Object.keys(macroDetail).length > 0 && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Cross-asset
          </div>
          <div className="pt-3 grid grid-cols-3 sm:grid-cols-5 gap-x-4 gap-y-2">
            {Object.entries(macroDetail).map(([k, m]) => {
              // yield indexes (TNX/TYX/IRX) move in bp — render the
              // points delta, not a % of the yield level
              const isYield = ['us10y', 'us30y', 'ust3m'].includes(k)
              return (
                <div key={k}>
                  <div className="text-[10px] uppercase tracking-wider text-faint">
                    {k.replace(/_/g, ' ')}
                  </div>
                  <div className="font-mono text-[12px] text-ink">
                    {m.value != null ? m.value : '—'}
                  </div>
                  {isYield && m.delta5d != null ? (
                    <div
                      className={`font-mono text-[10px] ${m.delta5d <= 0 ? 'text-constructive' : 'text-defensive'
                        }`}
                    >
                      5d {m.delta5d >= 0 ? '+' : ''}{Math.round(m.delta5d * 100)}bp
                    </div>
                  ) : m.chg5d != null && (
                    <div
                      className={`font-mono text-[10px] ${m.chg5d >= 0 ? 'text-constructive' : 'text-defensive'
                        }`}
                    >
                      5d {m.chg5d >= 0 ? '+' : ''}{(m.chg5d * 100).toFixed(1)}%
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Assets pulse — two-layer engine: shared macro regime +
          per-asset fundamental/fear scores. Metals get the precious/
          industrial read, crypto gets the liquidity-sponge read —
          same inputs, per-class interpretation. Fear is the entry
          window; intact structural demand is the thesis. Advisory
          accumulation reads, never orders. */}
      {metals?.today && (metals.today.metals || metals.today.crypto) &&
        (Object.keys(metals.today.metals ?? {}).length +
          Object.keys(metals.today.crypto ?? {}).length > 0) && (
          <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
            <div className="flex items-baseline justify-between">
              <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
                Assets pulse
              </div>
              <div className="flex items-baseline gap-3">
                {metals.today.macro?.label && (
                  <Chip
                    label={metals.today.macro.label.replace(/_/g, ' ')}
                    tone={
                      metals.today.macro.label === 'precious_bullish' ||
                        metals.today.macro.label === 'industrial_bullish'
                        ? 'ok'
                        : metals.today.macro.label === 'neutral'
                          ? 'off'
                          : 'warn'
                    }
                  />
                )}
                {metals.today.macro?.crypto_label && (
                  <Chip
                    label={`crypto: ${metals.today.macro.crypto_label.replace(/_/g, ' ')}`}
                    tone={
                      metals.today.macro.crypto_label === 'liquidity_sponge'
                        ? 'ok'
                        : metals.today.macro.crypto_label === 'neutral'
                          ? 'off'
                          : 'warn'
                    }
                  />
                )}
                {metals.today.age_days != null && (
                  <span className="font-mono text-[11px] text-faint">
                    {metals.today.age_days}d old
                  </span>
                )}
              </div>
            </div>
            {Array.isArray(metals.today.macro?.drivers) &&
              metals.today.macro.drivers.length > 0 && (
                <p className="pt-2 text-[11px] text-muted">
                  {metals.today.macro.drivers.join(' · ')}
                </p>
              )}
            {/* the turn — "conditions just formed" banners, the
                signal that matters for starting accumulation */}
            {(metals.today.transitions?.macro_flipped ||
              metals.today.transitions?.crypto_label_flipped ||
              Object.values(metals.today.transitions?.assets ?? {})
                .some((t) => t.newly_actionable)) && (
                <div className="pt-3 flex flex-wrap gap-2">
                  {metals.today.transitions?.macro_flipped && (
                    <Chip
                      label={`regime turned: ${String(
                        metals.today.transitions.macro_prev,
                      ).replace(/_/g, ' ')} → ${String(
                        metals.today.transitions.macro_now,
                      ).replace(/_/g, ' ')}`}
                      tone="ok"
                    />
                  )}
                  {metals.today.transitions?.crypto_label_flipped && (
                    <Chip
                      label={`crypto regime: ${String(
                        metals.today.transitions.crypto_label_prev,
                      ).replace(/_/g, ' ')} → ${String(
                        metals.today.transitions.crypto_label_now,
                      ).replace(/_/g, ' ')}`}
                      tone="ok"
                    />
                  )}
                  {Object.entries(
                    metals.today.transitions?.assets ?? {},
                  )
                    .filter(([, t]) => t.newly_actionable)
                    .map(([k, t]) => (
                      <Chip
                        key={k}
                        label={`${k} newly actionable: ${String(
                          t.verdict_prev ?? '—',
                        ).replace(/_/g, ' ')} → ${String(
                          t.verdict_now ?? '—',
                        ).replace(/_/g, ' ')}`}
                        tone="ok"
                      />
                    ))}
                </div>
              )}
            <div className="pt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                ...Object.entries(metals.today.metals ?? {}),
                ...Object.entries(metals.today.crypto ?? {}),
              ].map(([k, m]) => {
                const vTone =
                  m.verdict === 'strong_accumulate' ||
                    m.verdict === 'accumulate'
                    ? 'text-constructive'
                    : m.verdict === 'reduce'
                      ? 'text-defensive'
                      : 'text-neutral'
                const pos =
                  m.hi_52w != null && m.lo_52w != null && m.price != null &&
                    m.hi_52w > m.lo_52w
                    ? Math.round(
                      ((m.price - m.lo_52w) / (m.hi_52w - m.lo_52w)) * 100,
                    )
                    : null
                return (
                  <div key={k} className="rounded-lg border border-hairline px-4 py-3">
                    <div className="flex items-baseline justify-between">
                      <span className="text-[12px] font-medium uppercase tracking-wider text-ink">
                        {k}
                        {m.class === 'crypto' && (
                          <span className="ml-1.5 text-[8px] text-faint normal-case">
                            crypto
                          </span>
                        )}
                      </span>
                      <span className={`font-mono text-[12px] ${vTone}`}>
                        {(m.verdict ?? '—').replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="pt-2 flex items-baseline gap-4">
                      <span className="font-mono text-lg text-ink">
                        {m.opportunity != null ? m.opportunity : '—'}
                      </span>
                      <span className="font-mono text-[10px] text-faint">
                        fund {m.fundamental ?? '—'} · fear {m.fear ?? '—'}
                      </span>
                      {pos != null && (
                        <span className="ml-auto font-mono text-[10px] text-faint">
                          {pos}% of 52w range
                        </span>
                      )}
                    </div>
                    <div className="pt-1 flex items-baseline gap-3 font-mono text-[10px] text-faint">
                      {m.price != null && <span>{m.price}</span>}
                      {m.off_52w_high_pct != null && (
                        <span>
                          {(m.off_52w_high_pct * 100).toFixed(1)}% off high
                        </span>
                      )}
                      {m.rsi14 != null && (
                        <span>rsi {Math.round(m.rsi14)}</span>
                      )}
                      {k === 'silver' && metals.today?.gs_ratio_pctile != null && (
                        <span>G/S {Math.round(metals.today.gs_ratio_pctile)}th pctl</span>
                      )}
                      {m.falling_knife && (
                        <span className="text-caution">falling knife</span>
                      )}
                    </div>
                    {m.reason && (
                      <p className="pt-2 text-[10px] leading-relaxed text-ink">
                        {m.reason}
                      </p>
                    )}
                    {/* leg evidence — the actual input values the
                        score used, not just the number */}
                    {Array.isArray(m.legs?.fundamental) &&
                      m.legs.fundamental.length > 0 && (
                        <div className="pt-1.5 space-y-0.5">
                          {m.legs.fundamental.slice(0, 4).map((l) => (
                            <div key={l.name}
                              className="flex items-baseline gap-1.5 font-mono text-[9px]">
                              <span className="text-faint w-24 truncate">
                                {String(l.name ?? '').replace(/_/g, ' ')}
                              </span>
                              <span className="text-muted truncate">{l.value}</span>
                              <span className="ml-auto text-faint">{l.score}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    {m.thesis && (
                      <p className="pt-2 text-[10px] leading-relaxed text-muted">
                        {m.thesis}
                      </p>
                    )}
                    {Array.isArray(m.recovery_drivers) &&
                      m.recovery_drivers.length > 0 && (
                        <p className="pt-1 text-[10px] text-faint">
                          reprices on: {m.recovery_drivers[0]}
                          {m.recovery_drivers.length > 1 &&
                            ` · ${m.recovery_drivers[1]}`}
                        </p>
                      )}
                    {Array.isArray(m.missing) && m.missing.length > 0 && (
                      <p className="pt-1 text-[10px] text-faint">
                        missing: {m.missing.slice(0, 3).join(', ')}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
            <p className="pt-3 text-[10px] text-faint">
              nightly · fear entry needs intact fundamentals — supply
              fundamentals (COT, inventories, ETF flows, network usage)
              flagged per metal · advisory, never an order
            </p>
          </section>
        )}

      {/* expandable depth */}
      <div className="mt-10">
        {capex?.components != null &&
          typeof capex.components === 'object' && (
            <Section title="Capex legs" subtitle="≥50 counts as elevated">
              <div className="divide-y divide-transparent">
                {Object.entries(
                  capex.components as Record<string, unknown>,
                ).map(([k, v]) => (
                  <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
              </div>
            </Section>
          )}
        {buckets && (
          <Section title="What's driving it" subtitle="regime inputs">
            <div className="divide-y divide-transparent">
              {Object.entries(buckets)
                .filter(([k]) => !['structural', 'indexes', 'evidence',
                  '_confirmation', 'forward'].includes(k))
                .map(([k, v]) => (
                  <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
                ))}
            </div>
          </Section>
        )}

        {record.length > 0 && (
          <Section title="Track record" subtitle={`${record.length} graded`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-faint">
                    {Object.keys(record[0]).slice(0, 6).map((c) => (
                      <th key={c} className="pb-2 pr-4 font-medium">
                        {c.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {record.slice(0, 10).map((r, i) => (
                    <tr key={i} className="border-t border-hairline/60">
                      {Object.values(r).slice(0, 6).map((v, j) => (
                        <td key={j} className="py-2 pr-4 font-mono text-muted">
                          {fmtShort(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {todayExtras.length > 0 && (
          <Section title="Full context" subtitle="engine detail">
            <div className="divide-y divide-transparent">
              {todayExtras.map(([k, v]) => (
                <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
              ))}
            </div>
          </Section>
        )}

        {fwd?.market?.horizons != null && (
            <Section
              title="Forward outlook — historical analogs"
              subtitle={`${fwd.market.analogs?.length ?? 0} nearest market states · as of ${fwd.market.as_of ?? '—'} · observed outcomes, not a calibrated model`}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-faint text-left">
                      <th className="py-1 pr-3">horizon</th>
                      <th className="py-1 pr-3">median</th>
                      <th className="py-1 pr-3">p25 / p75</th>
                      <th className="py-1 pr-3">% positive</th>
                      <th className="py-1 pr-3">worst</th>
                      <th className="py-1">n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(fwd.market.horizons as Record<string, { n?: number; median_pct?: number; p25_pct?: number; p75_pct?: number; pct_positive?: number; worst_pct?: number; low_evidence?: boolean }>).map(([h, s]) => (
                      <tr key={h} className="border-t border-hairline/50">
                        <td className="py-1.5 pr-3 text-muted">{h}</td>
                        <td className={`py-1.5 pr-3 ${(s.median_pct ?? 0) >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                          {s.median_pct != null ? `${s.median_pct > 0 ? '+' : ''}${s.median_pct}%` : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-muted">
                          {s.p25_pct}% / {s.p75_pct}%
                        </td>
                        <td className="py-1.5 pr-3">{s.pct_positive ?? '—'}%</td>
                        <td className="py-1.5 pr-3 text-defensive">{s.worst_pct ?? '—'}%</td>
                        <td className="py-1.5">
                          {s.n ?? 0}
                          {s.low_evidence && (
                            <span className="ml-1 text-caution">low n</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pt-2 text-[10px] font-mono text-faint">
                analogs: {fwd.market.analogs?.map(a => a.date).join(', ')}
                {fwd.market.current_state && (
                  <> · state vix {fwd.market.current_state.vix} vs50 {fwd.market.current_state.vs50} vs200 {fwd.market.current_state.vs200}</>
                )}
              </div>
            </Section>
          )}

          {fwd?.event_study?.by_verdict != null && (
            <Section
              title="Earnings event study"
              subtitle={`${fwd.event_study.events_n ?? 0} journaled prints — how prints actually traded afterward`}
              defaultOpen={false}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="text-faint text-left">
                      <th className="py-1 pr-3">verdict</th>
                      <th className="py-1 pr-3">+5d med</th>
                      <th className="py-1 pr-3">+20d med</th>
                      <th className="py-1 pr-3">+60d med</th>
                      <th className="py-1">n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(fwd.event_study.by_verdict as Record<string, Record<string, { n?: number; median_pct?: number; pct_positive?: number; low_evidence?: boolean }>>).map(([v, hz]) => (
                      <tr key={v} className="border-t border-hairline/50">
                        <td className="py-1.5 pr-3 text-muted">{v}</td>
                        {(['5d', '20d', '60d'] as const).map(h => (
                          <td key={h} className={`py-1.5 pr-3 ${(hz[h]?.median_pct ?? 0) >= 0 ? 'text-aggressive' : 'text-defensive'}`}>
                            {hz[h]?.median_pct != null ? `${hz[h].median_pct! > 0 ? '+' : ''}${hz[h].median_pct}%` : '—'}
                            {hz[h]?.low_evidence && <span className="ml-1 text-caution text-[9px]">*</span>}
                          </td>
                        ))}
                        <td className="py-1.5">{hz['5d']?.n ?? hz['20d']?.n ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

        {!posture && !today && (
          <Section title="Status" defaultOpen>
            <p className="text-sm text-muted">
              No regime data returned — the worker may be unreachable or
              today&apos;s snapshot hasn&apos;t run yet (morning-regime
              fires 8:00 ET).
            </p>
          </Section>
        )}
      </div>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — deterministic posture, human decides</span>
        <span className="font-mono">
          {verdict?.confirmation ? `x-asset ${String(verdict.confirmation)}` : ''}
        </span>
      </footer>
    </main>
  )
}
