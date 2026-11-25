import { api, type HorizonScenario, type RegimeVerdict } from '@/lib/api'
import { glossed } from '@/lib/terms'
import { Chip, Kv, Section, Stat, fmtShort } from '@/components/regime'
import { VolChips } from '@/components/vol-chips'
import { TapeChips } from '@/components/tape-chips'
import { SessionTape } from '@/components/session-tape'
import { RetryRefresh } from '@/components/retry-refresh'
import { RecoveryPanel } from '@/components/recovery-panel'

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
  const movement = morning?.movement
  const valuation = morning?.valuation
  const eqPosture = morning?.posture
  const rates = morning?.rates
  const direction = morning?.direction
  const outlook = morning?.outlook
  const sec1d = [...(movement?.sectors ?? [])]
    .filter((s) => s.vs_spy1 != null)
    .sort((a, b) => (b.vs_spy1 ?? 0) - (a.vs_spy1 ?? 0))
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
  const liqFwd =
    structural && typeof structural.liquidity_forward === 'object' && structural.liquidity_forward !== null
      ? (structural.liquidity_forward as Record<string, unknown>)
      : null
  const stab =
    structural && typeof structural.market_stability === 'object' && structural.market_stability !== null
      ? (structural.market_stability as Record<string, unknown>)
      : null
  const synth =
    structural && typeof structural.market_synthesis === 'object' && structural.market_synthesis !== null
      ? (structural.market_synthesis as Record<string, unknown>)
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
  // the fine permission gate can be tighter than the coarse posture
  // flag — 'new longs ✓' is misleading when only selective setups at
  // reduced size are permitted. Reconcile: the fine gate wins.
  const selectiveLongsOnly =
    permissions?.normal_long === false &&
    permissions?.selective_long === true
  const shortsOff =
    permissions?.shorts_allowed === false ||
    (p.shorts === false && permissions?.shorts_allowed !== true)
  const sizeCut =
    typeof permissions?.size_multiplier === 'number' &&
    (permissions.size_multiplier as number) < 1
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
    ? `engine ${glossed(String(canonical.label))}${canonical.secondary ? ' · ' + glossed(String(canonical.secondary)) : ''}`
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

  // ---- plain-English evidence breakdown ------------------------------
  // Each family the engine reads gets one line, written for a person
  // not a terminal. Votes are confirm/against the equity regime
  // signal — in a risk-off regime a 'confirm' is bad news and an
  // 'against' is the silver lining, so the tone flips with the regime.
  const bearishRegime = ['defensive', 'caution'].includes(label.toLowerCase()) ||
    ['stress', 'bear', 'risk_off'].includes(String(canonical?.label ?? ''))
  const confirmTone = bearishRegime ? 'text-defensive' : 'text-aggressive'
  const againstTone = bearishRegime ? 'text-muted' : 'text-caution'

  const volBucket =
    buckets && typeof buckets.volatility === 'object' && buckets.volatility !== null
      ? (buckets.volatility as Record<string, unknown>)
      : null
  const eventRisk = (verdict?.event_risk as string | undefined) ??
    (buckets?._event_risk as string | undefined) ?? null
  const fomcDays = typeof fedFomc?.days_away === 'number'
    ? (fedFomc.days_away as number) : null
  // journaled event window — CPI events carry an 'expected' print
  // when the Nowflation forecast covers the release month
  const evts = Array.isArray(buckets?.events)
    ? (buckets.events as Record<string, unknown>[]) : []
  const cpiEvt = evts.find((e) => e.kind === 'cpi' && typeof e.expected === 'number')
  const catalystBits = [
    fomcDays != null && fomcDays <= 21 ? `FOMC in ${fomcDays} days` : null,
    cpiEvt ? `CPI in ${cpiEvt.days_away}d — Nowflation expects ${Number(cpiEvt.expected).toFixed(1)}%` : null,
  ].filter(Boolean).join(' · ')
  const chg5 = (k: string): string | null => {
    const v = macroDetail?.[k]?.chg5d ?? macroDetail?.[k]?.delta5d
    return typeof v === 'number' && Math.abs(v) >= 0.05
      ? ` (${v >= 0 ? '+' : ''}${v.toFixed(1)}% /5d)` : null
  }

  type EvidenceLine = { label: string; text: string; tone: string }
  const evidenceLines: EvidenceLine[] = []

  const creditVote = confVotes?.credit
  if (creditVote === 'confirm')
    evidenceLines.push({
      label: 'Credit', tone: confirmTone,
      text: `Investors are getting more worried about companies' ability to repay debt${chg5('hyg') ?? ''}.`,
    })
  else if (creditVote === 'against')
    evidenceLines.push({
      label: 'Credit', tone: againstTone,
      text: `Credit markets aren't showing stress — lenders aren't demanding more to hold corporate debt${chg5('hyg') ?? ''}.`,
    })

  const ratesVote = confVotes?.yields_10y ?? confVotes?.duration
  if (ratesVote === 'confirm')
    evidenceLines.push({
      label: 'Rates', tone: confirmTone,
      text: `Interest-rate conditions are putting pressure on stocks${chg5('us10y') ?? ''}.`,
    })
  else if (ratesVote === 'against')
    evidenceLines.push({
      label: 'Rates', tone: againstTone,
      text: `Rate conditions aren't adding pressure — yields are steady or helping stocks${chg5('us10y') ?? ''}.`,
    })

  const volLabel = String(volBucket?.label ?? '')
  if (volLabel.includes('ris')) {
    evidenceLines.push({
      label: 'Volatility', tone: 'text-defensive',
      text: `Market uncertainty and fear are increasing${chg5('vvix') ?? ''}.`,
    })
  } else if (volLabel.includes('fall') || volLabel === 'low') {
    evidenceLines.push({
      label: 'Volatility', tone: 'text-aggressive',
      text: `Market fear is receding${chg5('vvix') ?? ''}.`,
    })
  } else if (volLabel && volLabel !== 'normal') {
    evidenceLines.push({
      label: 'Volatility', tone: 'text-muted',
      text: `Volatility reads ${volLabel.replace(/_/g, ' ')}${chg5('vvix') ?? ''}.`,
    })
  }

  if (eventRisk === 'high' || eventRisk === 'extreme') {
    evidenceLines.push({
      label: 'Major catalysts within days', tone: 'text-caution',
      text: `Important economic or company news is coming soon${catalystBits ? ` — ${catalystBits}` : ''}, which could cause sharp price movements.`,
    })
    if (volLabel.includes('ris'))
      evidenceLines.push({
        label: 'Overnight gaps possible', tone: 'text-caution',
        text: 'Stocks could open significantly higher or lower than the previous close.',
      })
  } else if (eventRisk === 'low' || eventRisk === 'none') {
    evidenceLines.push({
      label: 'Catalysts', tone: 'text-muted',
      text: 'No major catalysts in the next few days.',
    })
  }

  const capexAlert = String(capex?.alert ?? '')
  if (capexAlert === 'watch' || capexAlert === 'alert' || capexAlert === 'exit') {
    evidenceLines.push({
      label: 'Slower structural picture', tone: capexAlert === 'watch' ? 'text-caution' : 'text-defensive',
      text: `The longer-term outlook is also weakening — the capex cycle reads '${String(capex?.band ?? '')}' (${capexAlert.toUpperCase()}), not just short-term sentiment.`,
    })
  } else if (capex?.band) {
    evidenceLines.push({
      label: 'Structural picture', tone: 'text-aggressive',
      text: `The longer-term picture is still holding — the capex cycle reads '${String(capex.band)}' with no alert.`,
    })
  }

  // ---- what this means for an investor -------------------------------
  // Action bullets derived from the mechanical gates (permissions) and
  // the verdict rules — same source, written as plain imperatives.
  const stanceLabel =
    label === 'Defensive' ? 'Defensive market environment'
    : label === 'Caution' ? 'Cautious market environment'
    : label === 'Neutral' ? 'Mixed market environment'
    : 'Constructive market environment'

  const rules = (verdict?.rules ?? {}) as Record<string, unknown>
  const actionBullets: string[] = []
  if (permissions?.dip_buying === false || permissions?.dip_buying === 'off')
    actionBullets.push('Avoid aggressively buying falling stocks — wait for selling pressure to stabilize.')
  if (String(rules.cash ?? '').toUpperCase() === 'RAISE')
    actionBullets.push('Keep some cash available.')
  if (String(rules.hedge ?? '') === 'ACTIVATE_CRASH_RULES')
    actionBullets.push('Crash rules are armed — keep hedges on.')
  if (permissions?.normal_long === false && permissions?.selective_long === false)
    actionBullets.push('New long entries are closed — manage existing positions only.')
  else if (selectiveLongsOnly)
    actionBullets.push('Only selective long setups are permitted — no broad buying.')
  if (typeof permissions?.size_multiplier === 'number') {
    const mult = permissions.size_multiplier as number
    if (mult === 0)
      actionBullets.push('Position sizing is at zero — nothing buys today.')
    else if (mult < 1)
      actionBullets.push(`Position sizing is reduced — run smaller than normal (×${mult.toFixed(2)}).`)
  }
  if (eventRisk === 'high' || eventRisk === 'extreme')
    actionBullets.push('Be careful holding highly volatile stocks through major announcements.')
  if (permissions?.dip_buying === false || permissions?.dip_buying === 'off' || divergent)
    actionBullets.push('Look for confirmation before buying the dip.')
  if (String(rules.leaps ?? '') === 'RESTRICTED')
    actionBullets.push('Long-dated option buying is restricted.')
  if (String(rules.core ?? '').toUpperCase() === 'HOLD' && actionBullets.length === 0)
    actionBullets.push('Hold core positions — don\'t sell into weakness.')
  if (actionBullets.length === 0)
    actionBullets.push('Follow the plan — no special restrictions today.')

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
        {/* layered read — the coarse 5-class label alone can mislead:
            'neutral' can hide an engine 'transition', risk-off macro,
            and an intraday tape break all at once */}
        <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[11px]">
          {today?.regime && (
            <span className="text-faint">
              baseline <span className="text-muted">{glossed(today.regime)}</span>
            </span>
          )}
          {canonical?.label != null && String(canonical.label) !== today?.regime && (
            <span className="text-faint">
              engine <span className="text-muted">
                {glossed(String(canonical.label))}
                {canonical.secondary ? ` + ${glossed(String(canonical.secondary))}` : ''}
              </span>
            </span>
          )}
          {today?.ai_regime && today.ai_regime !== today?.regime && (
            <span className="text-faint">
              ai <span className="text-muted">{glossed(today.ai_regime)}</span>
            </span>
          )}
          {intraday?.state && (
            <span className="text-faint">
              now <span className={
                intraday.tone === 'bad' ? 'text-defensive'
                : intraday.tone === 'warn' ? 'text-caution'
                : intraday.tone === 'good' ? 'text-aggressive' : 'text-muted'
              }>{glossed(intraday.state)}</span>
            </span>
          )}
          {today?.score != null && (
            <span className="text-faint">
              score <span className="text-ink">{today.score}</span>
            </span>
          )}
          {today?.confidence != null && (
            <span className="text-faint">
              conf <span className={
                String(today.confidence) === 'low' ? 'text-caution' : 'text-ink'
              }>{String(today.confidence)}{typeof today.confidence === 'number' ? '%' : ''}</span>
            </span>
          )}
        </div>
        <div className="pt-6 flex flex-wrap gap-2">
          <Chip
            label={
              !p.new_longs
                ? 'No new longs'
                : selectiveLongsOnly
                  ? 'Selective longs'
                  : 'New longs'
            }
            on={!!p.new_longs}
          />
          <Chip label={shortsOff ? 'No new shorts' : 'Shorts'} on={!shortsOff} />
          {sizeCut && (
            <Chip
              label={`size ×${Number(permissions!.size_multiplier).toFixed(2)}`}
              tone="warn"
            />
          )}
          {permissions?.breakout_buying != null &&
            permissions.breakout_buying !== 'allowed' && (
              <Chip
                label={`breakouts ${String(permissions.breakout_buying)}`}
                tone="warn"
              />
            )}
          {permissions?.dip_buying === false && (
            <Chip label="dip-buying off" tone="warn" />
          )}
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
        {direction && (
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pt-2 text-xs"
            title={direction.direction_detail ?? undefined}>
            <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
              stocks
            </span>
            <span className={`font-semibold text-[13px] ${direction.direction_tone === 'ok'
              ? 'text-aggressive' : direction.direction_tone === 'warn'
                ? 'text-caution' : direction.direction_tone === 'bad'
                  ? 'text-defensive' : 'text-muted'}`}>
              {direction.direction_label ?? direction.direction}
            </span>
            {direction.direction_headline && (
              <span className="text-muted">
                {direction.direction_headline}
              </span>
            )}
          </div>
        )}
        {outlook && (
          <div className="pt-2 space-y-0.5 font-mono text-[11px]"
            title="the same evidence at three scales — each horizon uses only the legs that predict at that scale; journaled daily so each grades on its own clock">
            {([
              ['next day', outlook.next_day],
              ['1-2 wks', outlook.weeks],
              ['1-3 mos', outlook.months],
            ] as const).map(([h, o]) => o?.verdict && (
              <div key={h} className="flex items-baseline gap-x-2">
                <span className="text-faint w-14 shrink-0">{h}</span>
                <span className={`font-semibold ${
                  o.tone === 'ok' ? 'text-aggressive'
                  : o.tone === 'warn' ? 'text-caution'
                  : 'text-defensive'}`}>
                  {(o.verdict ?? '').replace(/_/g, ' ')}
                </span>
                <span className="text-faint">
                  {(o.evidence ?? []).join(' · ')}
                </span>
              </div>
            ))}
          </div>
        )}
        {valuation && (
          <div className="pt-2 text-xs" title={valuation.detail ?? undefined}>
            {valuation.stance && (
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-1"
                title={valuation.stance_detail ?? undefined}>
                <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                  equity
                </span>
                <span className={`font-semibold ${valuation.stance_tone === 'ok'
                  ? 'text-aggressive' : valuation.stance_tone === 'warn'
                    ? 'text-caution' : valuation.stance_tone === 'bad'
                      ? 'text-defensive' : 'text-muted'}`}>
                  {valuation.stance_label ?? valuation.stance.replace(/_/g, ' ')}
                </span>
                {valuation.stance_headline && (
                  <span className="text-muted">
                    {valuation.stance_headline}
                  </span>
                )}
              </div>
            )}
            {eqPosture && (
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-1"
                title={eqPosture.posture_detail ?? undefined}>
                <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                  posture
                </span>
                <span className={`font-semibold ${eqPosture.posture_tone === 'ok'
                  ? 'text-aggressive' : eqPosture.posture_tone === 'warn'
                    ? 'text-caution' : eqPosture.posture_tone === 'bad'
                      ? 'text-defensive' : 'text-muted'}`}>
                  {eqPosture.posture_label ?? eqPosture.posture}
                </span>
                {eqPosture.posture_headline && (
                  <span className="text-muted">
                    {eqPosture.posture_headline}
                  </span>
                )}
              </div>
            )}
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                valuation
              </span>
              {valuation.headline && (
                <span className={`font-medium ${valuation.verdict_tone === 'ok'
                  ? 'text-aggressive' : valuation.verdict_tone === 'warn'
                    ? 'text-caution' : valuation.verdict_tone === 'bad'
                      ? 'text-defensive' : 'text-muted'}`}>
                  {valuation.headline}
                </span>
              )}
            </div>
            <div className="pt-0.5 font-mono text-[11px] text-faint">
              {[
                valuation.spy_pe_trailing != null &&
                  `SPY ${valuation.spy_pe_trailing}× ttm`,
                valuation.tracked_fwd_pe != null &&
                  `fwd ${valuation.tracked_fwd_pe}×` +
                  (valuation.tracked_names
                    ? ` (${valuation.tracked_names} names)` : ''),
                valuation.tracked_ey_pct != null &&
                  `EY ${valuation.tracked_ey_pct}%`,
                valuation.tnx_yield_pct != null &&
                  `10Y ${Number(valuation.tnx_yield_pct).toFixed(2)}%`,
                valuation.ey_spread_pp != null &&
                  `premium ${valuation.ey_spread_pp > 0 ? '+' : ''}${valuation.ey_spread_pp}pp`,
                valuation.spread_change_1w_bps != null &&
                  `1w ${valuation.spread_change_1w_bps > 0 ? '+' : ''}${valuation.spread_change_1w_bps}bp`,
                valuation.spread_change_1m_bps != null &&
                  `1m ${valuation.spread_change_1m_bps > 0 ? '+' : ''}${valuation.spread_change_1m_bps}bp`,
                valuation.tnx_as_of && valuation.as_of &&
                  (Date.parse(valuation.as_of)
                    - Date.parse(valuation.tnx_as_of)) / 864e5 > 3 &&
                  `10Y as of ${valuation.tnx_as_of}`,
                (valuation.obs_n ?? 0) < 40 &&
                  `${valuation.obs_n ?? 0}d window`,
              ].filter(Boolean).join(' · ')}
            </div>
            {valuation.earnings_verdict && (
              <div className="pt-1.5"
                title={valuation.earnings_detail ?? undefined}>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                    earnings
                  </span>
                  {valuation.earnings_headline && (
                    <span className={`font-medium ${valuation.earnings_tone === 'ok'
                      ? 'text-aggressive' : valuation.earnings_tone === 'warn'
                        ? 'text-caution' : valuation.earnings_tone === 'bad'
                          ? 'text-defensive' : 'text-muted'}`}>
                      {valuation.earnings_headline}
                    </span>
                  )}
                </div>
                <div className="pt-0.5 font-mono text-[11px] text-faint">
                  {[
                    valuation.eps_rev_breadth != null &&
                      `breadth ${valuation.eps_rev_breadth >= 0 ? '+' : ''}${Math.round(valuation.eps_rev_breadth * 100)}%`,
                    valuation.eps_rev_n != null &&
                      `30d ${valuation.eps_rev_up_n ?? 0}↑/${valuation.eps_rev_down_n ?? 0}↓/${valuation.eps_rev_flat_n ?? 0}→`,
                    valuation.fwd_eps_growth_fy1_fy2 != null &&
                      `FY→FY ${valuation.fwd_eps_growth_fy1_fy2 >= 0 ? '+' : ''}${Math.round(valuation.fwd_eps_growth_fy1_fy2 * 100)}%`,
                  ].filter(Boolean).join(' · ')}
                </div>
              </div>
            )}
          </div>
        )}
        {rates && (
          <div className="pt-2 text-xs" title={rates.rates_detail ?? undefined}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                rates
              </span>
              <span className={`font-semibold ${rates.rates_tone === 'ok'
                ? 'text-aggressive' : rates.rates_tone === 'warn'
                  ? 'text-caution' : rates.rates_tone === 'bad'
                    ? 'text-defensive' : 'text-muted'}`}>
                {rates.rates_direction
                  ? rates.rates_direction === 'reheating'
                    ? 'Reheating'
                    : rates.rates_direction === 'cooling'
                      ? 'Cooling' : 'Steady'
                  : '—'}
              </span>
              {rates.rates_headline && (
                <span className="text-muted">{rates.rates_headline}</span>
              )}
            </div>
            <div className="pt-0.5 font-mono text-[11px] text-faint">
              {[
                rates.realtime_yoy != null &&
                  `nowcast ${rates.realtime_yoy}%` +
                  (rates.spark ? ` ${rates.spark}` : ''),
                rates.realtime_wow_pp != null &&
                  `wk ${rates.realtime_wow_pp > 0 ? '+' : ''}${rates.realtime_wow_pp}pp`,
                rates.rt_d30_pp != null &&
                  `mo ${rates.rt_d30_pp > 0 ? '+' : ''}${rates.rt_d30_pp}pp`,
                rates.official_yoy != null &&
                  `official ${rates.official_yoy}%` +
                  (rates.official_month ? ` (${rates.official_month})` : ''),
                rates.print_forecast_yoy != null &&
                  `next print ~${rates.print_forecast_yoy}%`,
              ].filter(Boolean).join(' · ')}
            </div>
            {(rates.drivers?.length || rates.wti_value != null) && (
              <div className="pt-0.5 font-mono text-[11px] text-faint">
                {[
                  rates.drivers?.length &&
                    'drivers ' + rates.drivers.slice(0, 4).map((d) =>
                      `${d.label ?? d.key} ${d.yoy}%` +
                      (d.state === 'hot' ? '↑hot'
                        : d.state === 'cool' ? '↓cool' : '')).join(' · '),
                  rates.wti_value != null &&
                    `oil $${rates.wti_value}` +
                    (rates.wti_chg5d != null
                      ? ` ${rates.wti_chg5d > 0 ? '+' : ''}${Math.round(rates.wti_chg5d * 100)}%/wk` : ''),
                ].filter(Boolean).join(' · ')}
              </div>
            )}
            <div className="pt-0.5 font-mono text-[11px] text-faint">
              {[
                rates.fed_expected_bps != null &&
                  `fed ${rates.fed_expected_bps > 0 ? '+' : ''}${rates.fed_expected_bps}bp ` +
                  `${(rates.fed_lean ?? '').replace(/_/g, ' ')}` +
                  (rates.bps_d7 != null
                    ? ` (${rates.bps_d7 > 0 ? '+' : ''}${rates.bps_d7}bp wk)` : ''),
                rates.p_hike != null &&
                  `hike ${rates.p_hike}%` +
                  (rates.p_hike_d7 != null
                    ? ` (${rates.p_hike_d7 > 0 ? '+' : ''}${rates.p_hike_d7}pts wk)` : ''),
                rates.p_cut != null && `cut ${rates.p_cut}%`,
                rates.fomc_date &&
                  `FOMC ${rates.fomc_date}` +
                  (rates.fomc_days != null ? ` ${rates.fomc_days}d` : ''),
              ].filter(Boolean).join(' · ')}
            </div>
          </div>
        )}
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

      {/* money movement — how long this regime has run, when it
          flipped, and which sectors are absorbing vs shedding flow.
          Composed read-time from journaled snapshots + stored bars;
          the SMH early-warning row appears once mig 210 lands. */}
      {movement && (movement.regime_clock || (movement.sectors?.length ?? 0) > 0) && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Money movement
          </div>
          {movement.regime_clock && (
            <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px]">
              <span className={
                movement.regime_clock.regime === 'stress' || movement.regime_clock.regime === 'risk_off'
                  ? 'font-medium text-defensive'
                  : movement.regime_clock.regime === 'strong_risk_on' || movement.regime_clock.regime === 'risk_on'
                    ? 'font-medium text-aggressive' : 'font-medium text-muted'
              }>
                {glossed(movement.regime_clock.regime)}
              </span>
              <span className="font-mono text-muted">
                day {movement.regime_clock.days ?? '—'} · began {movement.regime_clock.since ?? '—'}
                {movement.regime_clock.prev && ` · was ${glossed(movement.regime_clock.prev)}`}
              </span>
            </div>
          )}
          {movement.smh_ew && movement.smh_ew.risk != null && (
            <p className="pt-1.5 text-[11px] leading-relaxed text-muted">
              <span className="text-faint">SMH leadership </span>
              <span className={
                (movement.smh_ew.risk ?? 0) >= 55 ? 'text-defensive'
                : (movement.smh_ew.risk ?? 0) >= 40 ? 'text-caution' : 'text-muted'
              }>
                risk {movement.smh_ew.risk} · {glossed(movement.smh_ew.state)}
              </span>
              {(movement.smh_ew.destinations?.length ?? 0) > 0 &&
                ` — capital leaning toward ${movement.smh_ew!.destinations!.join(', ')}`}
            </p>
          )}
          {(movement.sectors?.length ?? 0) > 0 && (
            <div className="pt-3 space-y-1 font-mono text-[11px]">
              {sec1d.length > 0 && (
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <span className="text-faint">sectors vs SPY · latest</span>
                  <span className="text-aggressive">
                    in {sec1d.slice(0, 3).map((s) =>
                      `${s.symbol} ${(s.vs_spy1 ?? 0) >= 0 ? '+' : ''}${((s.vs_spy1 ?? 0) * 100).toFixed(1)}%`
                    ).join('  ')}
                  </span>
                  <span className="text-defensive">
                    out {sec1d.slice(-3).reverse().map((s) =>
                      `${s.symbol} ${(s.vs_spy1 ?? 0) >= 0 ? '+' : ''}${((s.vs_spy1 ?? 0) * 100).toFixed(1)}%`
                    ).join('  ')}
                  </span>
                </div>
              )}
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="text-faint">sectors vs SPY · 5d</span>
                <span className="text-aggressive">
                  in {movement.sectors!.slice(0, 3).map((s) =>
                    `${s.symbol} ${s.vs_spy5 != null && s.vs_spy5 >= 0 ? '+' : ''}${s.vs_spy5 != null ? (s.vs_spy5 * 100).toFixed(1) : '—'}%`
                  ).join('  ')}
                </span>
                <span className="text-defensive">
                  out {movement.sectors!.slice(-3).reverse().map((s) =>
                    `${s.symbol} ${s.vs_spy5 != null && s.vs_spy5 >= 0 ? '+' : ''}${s.vs_spy5 != null ? (s.vs_spy5 * 100).toFixed(1) : '—'}%`
                  ).join('  ')}
                </span>
              </div>
            </div>
          )}
          {(movement.flips?.length ?? 0) > 0 && (
            <p className="pt-2 text-[10px] text-faint">
              flips {movement.flips!.map((f) =>
                `${f.as_of}: ${glossed(f.from)} → ${glossed(f.to)}`
              ).join(' · ')}
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
            <p className="pt-3 text-[15px] leading-relaxed text-ink">
              {verdict.plain}
            </p>
          )}
          {/* timing layer — the call is the daily plan; this is what
              the live tape says to do THIS hour (refreshes intraday) */}
          {intraday?.action && (
            <p className="pt-2 text-[12px] leading-relaxed">
              <span className="text-faint">right now · </span>
              <span className={
                intraday.tone === 'bad' ? 'text-defensive'
                : intraday.tone === 'warn' ? 'text-caution'
                : intraday.tone === 'good' ? 'text-aggressive' : 'text-muted'
              }>
                {(intraday.state ?? '').replace(/_/g, ' ')} — {intraday.action}
              </span>
            </p>
          )}

          {/* the evidence — one plain-English line per family the
              engine read, toned by whether it confirms the regime */}
          {evidenceLines.length > 0 && (
            <ul className="pt-4 space-y-1.5">
              {evidenceLines.map((l) => (
                <li key={l.label} className="flex gap-2 text-[13px] leading-relaxed">
                  <span className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${l.tone.replace('text-', 'bg-')}`} />
                  <span className="text-muted">
                    <span className="font-medium text-ink">{l.label}:</span>{' '}
                    {l.text}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* what this means for an investor — the stance + the
              mechanical gates written as plain imperatives */}
          {actionBullets.length > 0 && (
            <div className="pt-4 mt-4 border-t border-hairline">
              <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
                What this means for an investor
              </div>
              <p className={`pt-2 text-[13px] font-medium ${tone}`}>
                {stanceLabel}
              </p>
              <ul className="pt-2 space-y-1.5">
                {actionBullets.map((b) => (
                  <li key={b} className="flex gap-2 text-[13px] leading-relaxed text-muted">
                    <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-faint" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              {/* the raw gate verbs stay visible — the bullets are the
                  translation, this is the deterministic source */}
              {Object.keys(rules).filter((k) => k !== 'note').length > 0 && (
                <p className="pt-3 font-mono text-[10px] tracking-wide text-faint">
                  {Object.entries(rules)
                    .filter(([k]) => k !== 'note')
                    .map(([k, v]) => `${k} ${String(v).replace(/_/g, ' ').toLowerCase()}`)
                    .join(' · ')}
                </p>
              )}
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

          {/* cross-asset confirmation — do other markets agree with
              the equity move? ✓ = votes the same direction as stocks,
              which can be a bearish consensus, not a bullish one —
              so the anchor (eq direction) is shown first */}
          {confVotes && Object.keys(confVotes).length > 0 && (() => {
            const spyRet5 =
              typeof indexes?.SPY?.ret5 === 'number' ? indexes.SPY.ret5 : null
            const eqDir = spyRet5 != null
              ? spyRet5 > 0.005 ? 'up' : spyRet5 < -0.005 ? 'down' : 'flat'
              : null
            const META: Record<string, {
              name: string; src?: string; on: string; off: string
            }> = {
              yields_10y: { name: '10Y', src: 'us10y',
                on: 'yields falling — supports stocks',
                off: 'yields rising — headwind' },
              dollar: { name: 'DXY', src: 'dxy',
                on: 'dollar easing — supports risk',
                off: 'dollar strong — headwind' },
              credit: { name: 'HYG', src: 'hyg',
                on: 'credit bid — appetite intact',
                off: 'credit weak — stress building' },
              oil: { name: 'WTI', src: 'wti',
                on: 'oil firm — growth signal',
                off: 'oil soft — growth worry' },
              btc: { name: 'BTC', src: 'btc',
                on: 'crypto bid — appetite alive',
                off: 'crypto dumped — appetite weak' },
              vix: { name: 'VIX',
                on: 'fear easing', off: 'fear building' },
              duration: { name: 'TLT', src: 'tlt',
                on: 'bonds stable',
                off: 'rate stress / flight-to-safety' },
            }
            const items = Object.entries(confVotes).map(([k, v]) => {
              const m = META[k] ?? { name: k, on: '', off: '' }
              const src = m.src ? macroDetail?.[m.src] : null
              let move: string | null = null
              if (k === 'yields_10y' && src?.delta5d != null)
                move = `${src.delta5d >= 0 ? '+' : ''}${Math.round(src.delta5d * 100)}bp`
              else if (src?.chg5d != null)
                move = `${src.chg5d >= 0 ? '+' : ''}${(src.chg5d * 100).toFixed(1)}%`
              else if (k === 'vix' && p.vol?.vix != null)
                move = `${p.vol.vix.toFixed(1)}`
              // confirm = asset's risk read agrees with equity direction;
              // in a down market the confirming assets are the risk-off ones
              const riskOn =
                eqDir === 'down' ? v !== 'confirm'
                  : eqDir === 'up' ? v === 'confirm' : null
              return { k, v, m, move, riskOn }
            })
            const nConf = items.filter((i) => i.v === 'confirm').length
            const n = items.length
            const dissent = items.filter((i) => i.v !== 'confirm')
            const verdict =
              eqDir === 'down'
                ? nConf >= n * 0.7
                  ? `${nConf} of ${n} markets read risk-off (money moving to safety) alongside stocks — broad bearish consensus, not a lone wobble`
                  : nConf <= n * 0.4
                    ? `only ${nConf} of ${n} markets confirm the slide — the selloff may be equity-specific; watch for divergence`
                    : `${nConf} of ${n} markets confirm the slide — partial agreement`
                : eqDir === 'up'
                  ? nConf >= n * 0.7
                    ? `${nConf} of ${n} markets underwrite the rally — yields, credit and risk assets agree`
                    : nConf <= n * 0.4
                      ? `only ${nConf} of ${n} markets underwrite the rally — thin confirmation, treat breakouts with care`
                      : `${nConf} of ${n} markets underwrite the rally — partial support`
                  : `${nConf} of ${n} markets agree with a flat tape`
            return (
              <div className="pt-3">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
                    x-asset · do other markets agree with stocks?
                  </span>
                  {spyRet5 != null && (
                    <span className="font-mono text-[10px] text-faint">
                      anchor: SPY {spyRet5 >= 0 ? '+' : ''}{(spyRet5 * 100).toFixed(1)}%/5d
                    </span>
                  )}
                </div>
                <div className="pt-2 flex flex-wrap gap-1.5">
                  {items.map(({ k, v, m, move, riskOn }) => (
                    <span
                      key={k}
                      title={v === 'confirm' ? m.off && eqDir === 'down' ? m.off : m.on : (riskOn ? m.on : m.off) + ' — does not agree with stocks'}
                      className={`rounded-full border px-2.5 py-0.5 text-[11px] font-mono ${
                        v === 'confirm'
                          ? riskOn === false
                            ? 'border-defensive/40 text-defensive'
                            : 'border-aggressive/40 text-aggressive'
                          : 'border-caution/40 text-caution'
                        }`}
                    >
                      {m.name}{move ? ` ${move}` : ''}{' '}
                      <span className="text-faint">
                        {v === 'confirm' ? '✓ agrees' : '✗ disagrees'}
                      </span>
                    </span>
                  ))}
                </div>
                <p className={`pt-2 text-[11px] leading-relaxed ${
                  eqDir === 'down' && nConf >= n * 0.7
                    ? 'text-defensive'
                    : eqDir === 'up' && nConf >= n * 0.7
                      ? 'text-aggressive'
                      : 'text-muted'
                  }`}>
                  {verdict}
                  {dissent.length > 0 && (
                    <span className="text-faint">
                      {' '}Dissent: {dissent.map((d) => `${d.m.name} (${d.riskOn ? d.m.on : d.m.off})`).join('; ')}.
                    </span>
                  )}
                </p>
              </div>
            )
          })()}

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


      {/* session tape — how today unfolded: journaled 15-min states
          with the readings at each transition (the "gapped → rallied
          → faded — why" answer) */}
      {tape && <SessionTape tape={tape} />}

      {/* thin score strip */}
      {today && (
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-6 rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
          <Stat label="Regime" value={glossed(today.regime)} />
          <Stat
            label="Score"
            value={today.score != null ? String(today.score) : '—'}
          />
          <Stat
            label="Confidence"
            value={
              today.confidence != null
                ? typeof today.confidence === 'number'
                  ? `${today.confidence}%`
                  : String(today.confidence)
                : '—'
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
          buying vs relief rally vs failing. Rows expand to the
          session story: price-vs-vwap path + signal timeline +
          transitions, all journaled. */}
      {(irec?.symbols?.length ?? 0) > 0 && (
        <RecoveryPanel rows={irec!.symbols!} asOf={irec!.as_of}
          stale={irec!.stale} participation={irec!.participation} />
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
          {fragility.legs && Object.keys(fragility.legs).length > 0 && (
            <div className="pt-3 space-y-0.5 font-mono text-[11px]">
              <div className="text-faint"
                title="what's actually in the market's leverage — per-leg quantities with their honesty status. observed = measured, estimated = modeled proxy, missing = feed down (never counted as neutral).">
                how much leverage
              </div>
              {Object.entries(fragility.legs).map(([k, l]) => (
                <div key={k} className="text-faint">
                  <span className={
                    (l.score ?? 0) >= 60 ? 'text-defensive'
                    : (l.score ?? 0) >= 40 ? 'text-caution' : 'text-muted'}>
                    {k.replace(/_/g, ' ')}{l.score != null ? ` ${Math.round(l.score)}` : ' —'}
                  </span>
                  <span className={
                    l.status === 'observed' ? 'text-faint'
                    : l.status === 'estimated' ? 'text-caution' : 'text-faint'}>
                    {' · '}{l.status}
                  </span>
                  {l.read && <span>{' — '}{l.read}</span>}
                </div>
              ))}
              {fragility.leverage_cycle?.phase && (
                <div className="pt-1.5"
                  title={`leverage cycle phase — derived from ${Object.entries(fragility.leverage_cycle.basis ?? {}).filter(([, v]) => v).map(([k]) => k.replace(/_/g, ' ')).join(', ') || 'no active flags'} · discharge ${fragility.leverage_cycle.discharge_score ?? '—'} · exhaustion ${fragility.leverage_cycle.exhaustion_score ?? '—'}`}>
                  <span className={`font-mono text-[11px] ${
                    fragility.leverage_cycle.phase === 'firing' || fragility.leverage_cycle.phase === 'building'
                      ? 'text-defensive'
                      : fragility.leverage_cycle.phase === 'discharging'
                        ? 'text-caution' : 'text-aggressive'}`}>
                    leverage {fragility.leverage_cycle.phase}
                  </span>
                  <span className="text-[12px] text-muted">
                    {' — '}{fragility.leverage_cycle.what_to_do}
                  </span>
                </div>
              )}
              {fragility.validators && (
                <div className="text-faint pt-1"
                  title="slow/unavailable leverage feeds — disclosed, never silently absent">
                  {Object.entries(fragility.validators as Record<string, {status?: string; note?: string}>)
                    .filter(([, v]) => v?.status && v.status !== 'ok')
                    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v.status}`)
                    .join(' · ')}
                </div>
              )}
            </div>
          )}
          {(fragility.sectors?.length ?? 0) > 0 && (
            <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[11px]">
              <span className="text-faint"
                title="per-sector leverage concentration — lev-ETF crowding + trigger proximity + vol regime + relative deterioration (+ short-interest where journaled). Delta = score change vs the last journaled read.">
                fragile sectors
              </span>
              {fragility.sectors!.map((s) => (
                <span key={s.etf}
                  className={(s.band === 'critical' || s.band === 'fragile')
                    ? 'text-defensive'
                    : s.band === 'elevated'
                      ? 'text-caution' : 'text-faint'}
                  title={`${s.label} — ${s.score ?? '—'} ${s.band ?? ''}\nlegs: ${Object.entries(s.legs ?? {}).map(([k, v]) =>
                    v?.score != null ? `${k} ${v.score}` : `${k}: ${v?.note ?? v?.status ?? 'missing'}`).join(' · ')}`}>
                  {s.etf} {s.score ?? '—'}
                  {s.score_delta != null && s.score_delta !== 0 &&
                    ` (${s.score_delta > 0 ? '+' : ''}${s.score_delta})`}
                </span>
              ))}
            </div>
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
          {/* flow destination + sub-scores + recovery ladder — where
              is money actually going, kept as separate reads per the
              spec (never averaged into the headline) */}
          {(() => {
            const fm = liq.flow_matrix as Record<string, unknown> | undefined
            const subs = liq.sub_scores as Record<string, number | null> | undefined
            const rec = liq.recovery as Record<string, unknown> | undefined
            const steps = (rec?.steps as Array<Record<string, unknown>>) || []
            return (
              <>
                {fm?.destination != null && (
                  <div className="pt-2 text-[11px]">
                    <span className="text-faint">flow destination </span>
                    <span className={liqChipTone(String(fm.destination).includes('safety') || String(fm.destination).includes('outflow') ? 'decelerating' : 'improving')}>
                      {String(fm.destination).replace(/_/g, ' ')}
                    </span>
                  </div>
                )}
                {subs && (
                  <div className="pt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] font-mono">
                    {(['liquidity', 'credit_stress', 'equity_flows',
                       'market_confirmation', 'recovery'] as const)
                      .filter(k => subs[k] != null)
                      .map(k => (
                        <span key={k}>
                          <span className="text-faint">{k.replace(/_/g, ' ')} </span>
                          <span className={(subs[k] as number) >= 65 ? 'text-aggressive'
                            : (subs[k] as number) >= 45 ? 'text-caution' : 'text-defensive'}>
                            {String(subs[k])}
                          </span>
                        </span>
                      ))}
                  </div>
                )}
                {steps.length > 0 && (
                  <div className="pt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px]"
                    title="recovery confirmation sequence — partial order is honest, not a verdict">
                    <span className="text-faint">recovery </span>
                    {steps.map(s => (
                      <span key={String(s.step)}
                        title={String(s.detail || '')}
                        className={s.met ? 'text-aggressive' : 'text-faint'}>
                        {s.met ? '✓' : '·'} {String(s.step).replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </>
            )
          })()}
          {/* forward outlook — projected liquidity at 4/8/12w,
              labeled 'projected' (uncalibrated); confidence shown
              beside, never merged into the live score */}
          {liqFwd && (() => {
            const hz = (liqFwd.horizons ?? {}) as Record<string, Record<string, unknown>>
            const sched = (liqFwd.scheduled ?? {}) as Record<string, unknown>
            return (
              <div className="pt-3 border-t border-hairline mt-2">
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[11px]">
                  <span className="text-faint uppercase tracking-wider text-[10px]">forward</span>
                  {(['4w', '8w', '12w'] as const).map(h => {
                    const v = hz[h] || {}
                    const s = v.projected_liquidity_score as number | null
                    const c = v.projected_liquidity_confidence as number | null
                    return s != null ? (
                      <span key={h} title={`band ${String(v.band ?? '')} — confidence ${c ?? '?'} (uncalibrated)`}>
                        <span className="text-faint">{h} </span>
                        <span className={s >= 65 ? 'text-aggressive' : s >= 45 ? 'text-caution' : 'text-defensive'}>
                          {String(s)}
                        </span>
                        <span className="text-faint text-[10px]">·{c != null ? Math.round(c * 100) + '%' : '?'}</span>
                      </span>
                    ) : null
                  })}
                  {liqFwd.posture_hint != null && (
                    <span>
                      <span className="text-faint">8w hint </span>
                      <span className={liqChipTone(String(liqFwd.posture_hint) === 'supportive' ? 'improving' : String(liqFwd.posture_hint) === 'defensive' || String(liqFwd.posture_hint) === 'caution' ? 'decelerating' : '')}>
                        {String(liqFwd.posture_hint).replace(/_/g, ' ')}
                      </span>
                    </span>
                  )}
                </div>
                {sched && (
                  <div className="pt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-faint">
                    {sched.weeks_to_rrp_zero != null &&
                      <span>RRP empties ~{String(sched.weeks_to_rrp_zero)}wk</span>}
                    {sched.rrp_buffer_depleted === true &&
                      <span className="text-caution">RRP buffer empty</span>}
                    {sched.tga_refill_b_wk != null && Number(sched.tga_refill_b_wk) > 0 &&
                      <span>TGA refill {String(sched.tga_refill_b_wk)}B/wk</span>}
                    {sched.qt_measured_b_wk != null && Number(sched.qt_measured_b_wk) > 0 &&
                      <span>QT ~{String(sched.qt_measured_b_wk)}B/wk</span>}
                  </div>
                )}
              </div>
            )
          })()}
          {/* market stability — are buyers returning TODAY; raw
              observations, separate question from the forward read */}
          {stab && stab.stability_label != null && (
            <div className="pt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[11px]">
              <span className="text-faint uppercase tracking-wider text-[10px]">stability</span>
              <span className={liqChipTone(stab.stability_label === 'stable' ? 'improving' : stab.stability_label === 'unstable' ? 'decelerating' : '')}>
                {String(stab.stability_label)}
              </span>
              {stab.qqq_minutes_above_vwap != null &&
                <span className="text-faint">QQQ {String(stab.qqq_minutes_above_vwap)}m{'>'}vwap</span>}
              {stab.vix != null &&
                <span className="text-faint">vix {String(stab.vix)}</span>}
              {stab.breadth_adv_pct != null &&
                <span className="text-faint">breadth {String(stab.breadth_adv_pct)}%</span>}
              {stab.stable_sessions != null && Number(stab.stable_sessions) > 0 &&
                <span className="text-aggressive">{String(stab.stable_sessions)}d stable</span>}
              {stab.journaled_mark != null &&
                <span className="text-faint text-[10px]">@{String(stab.journaled_mark)}</span>}
            </div>
          )}
          {/* synthesis — the three-question verdict, shadow mode */}
          {synth?.regime != null && (
            <div className="pt-2 text-[11px]">
              <span className="text-faint">regime </span>
              <span className={liqChipTone(synth.regime === 'recovery_attempt' ? 'improving' : synth.regime === 'severe_warning' || synth.regime === 'defensive' ? 'decelerating' : '')}>
                {String(synth.regime).replace(/_/g, ' ')}
              </span>
              {synth.posture_hint != null &&
                <span className="text-faint"> — {String(synth.posture_hint)}</span>}
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
