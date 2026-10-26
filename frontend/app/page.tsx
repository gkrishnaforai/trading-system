import { api, type HorizonScenario, type RegimeVerdict } from '@/lib/api'
import { Chip, Kv, Section, Stat, fmtShort } from '@/components/regime'
import { VolChips } from '@/components/vol-chips'
import { TapeChips } from '@/components/tape-chips'
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

export default async function RegimePage() {
  const [posture, morning, tape, alarms] = await Promise.all([
    api.posture(),
    api.morningRegime(),
    api.intraday(),
    api.correctionAlarms(),
  ])

  const p = posture ?? {}
  const today = morning?.today
  const record = morning?.record ?? []

  const tone = TONE[p.posture ?? 'neutral'] ?? 'text-neutral'
  const label = LABEL[p.posture ?? 'neutral'] ?? 'Unknown'
  // today's morning snapshot is what this card renders — the posture
  // journal (regime_snapshots) refreshes overnight and can lag a day;
  // let the fresher read own the header date
  const asOf = today?.as_of || p.regime_as_of

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
        <span className="font-mono text-xs text-faint">{fmtDate(asOf)}</span>
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

      {/* verdict — the plain-English call + action rules */}
      {(verdict?.plain || (verdict?.rules && Object.keys(verdict.rules).length > 0)) && (
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
        {indexes && Object.keys(indexes).length > 0 && (
          <Section
            title="Index technicals"
            subtitle={
              breadthBucket?.divergence != null
                ? `large-cap ${breadthBucket.large_cap ?? '—'}% vs broad ${breadthBucket.broad ?? '—'}% above 50d`
                : 'core US set + global overlay'
            }
          >
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(indexes).map(([sym, ix]) => {
                const num = (k: string) =>
                  typeof ix?.[k] === 'number' ? (ix[k] as number) : null
                const rsi = num('rsi14')
                const overlay = ix?.overlay === true
                return (
                  <div
                    key={sym}
                    className="rounded-md border border-hairline/60 px-3 py-2"
                  >
                    <div className="flex items-baseline justify-between">
                      <span className="text-[13px] font-semibold">{sym}</span>
                      <span className="font-mono text-[11px] text-faint">
                        {overlay ? 'overlay' : rsi != null ? `RSI ${rsi.toFixed(0)}` : ''}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-[12px] text-muted">
                      {num('price')?.toFixed(2) ?? '—'}
                    </div>
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
          </Section>
        )}
        {buckets && (
          <Section title="What's driving it" subtitle="regime inputs">
            <div className="divide-y divide-transparent">
              {Object.entries(buckets)
                .filter(([k]) => k !== 'structural' && k !== 'indexes')
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

        {!posture && !today && (
          <Section title="Status" defaultOpen>
            <p className="text-sm text-muted">
              No regime data returned — the worker may be unreachable or
              today&apos;s snapshot hasn&apos;t run yet (morning-regime
              fires 9:15 ET).
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
