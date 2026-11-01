import { api, type ThemeCard } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** Theme Intelligence — ranks themes by expected 6-12m opportunity:
 *  scenario-weighted macro fit + earnings/revisions + valuation +
 *  demand + momentum + resilience. The index prices realized
 *  performance; this page prices expected opportunity — a theme can
 *  be winning and still be a poor place for new capital. Advisory,
 *  deterministic, journaled weekly. */

const VERDICT_TONE: Record<string, string> = {
  strong: 'text-aggressive',
  attractive: 'text-constructive',
  selective: 'text-caution',
  watch: 'text-neutral',
  avoid: 'text-defensive',
  no_score: 'text-faint',
}

const STAGE_TONE: Record<string, string> = {
  emerging: 'bg-caution/15 text-caution',
  inflecting: 'bg-constructive/15 text-constructive',
  mainstream: 'bg-hairline/60 text-muted',
  exhausted: 'bg-defensive/15 text-defensive',
  watching: 'bg-hairline/60 text-muted',
}

function num(v?: number | null, suffix = '') {
  return v == null ? '—' : `${v}${suffix}`
}

function ScenarioStrip({ probs }: { probs: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1">
      {Object.entries(probs).map(([k, p]) => (
        <span key={k} className="text-[11px]">
          <span className="text-faint">{k.replace(/_/g, ' ')}</span>{' '}
          <span className="font-mono text-ink">{p}%</span>
        </span>
      ))}
    </div>
  )
}

function ThemeRow({ k, t }: { k: string; t: ThemeCard }) {
  const tone = VERDICT_TONE[t.verdict ?? 'watch'] ?? 'text-neutral'
  const stage = STAGE_TONE[t.stage ?? ''] ?? 'bg-hairline/60 text-muted'
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <span className="text-[14px] font-semibold text-ink">
            {t.name ?? k}
          </span>
          {t.stage && (
            <span className={`ml-2 rounded-full px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider ${stage}`}>
              {t.stage}
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-3">
          <span className={`font-mono text-xl ${tone}`}>
            {num(t.opportunity)}
          </span>
          <span className={`font-mono text-[11px] uppercase ${tone}`}>
            {(t.verdict ?? '—').replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      <div className="pt-2 grid grid-cols-3 gap-4">
        <div>
          <div className="text-[9px] uppercase tracking-wider text-faint">expected</div>
          <div className="font-mono text-[13px] text-ink">{num(t.expected)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-wider text-faint">downside</div>
          <div className="font-mono text-[13px] text-ink">{num(t.downside)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-wider text-faint">robustness</div>
          <div className="font-mono text-[13px] text-ink">{num(t.robustness)}</div>
        </div>
      </div>

      {Array.isArray(t.legs) && t.legs.length > 0 && (
        <div className="pt-3 flex flex-wrap gap-x-4 gap-y-1">
          {t.legs.map((l) => (
            <span key={l.name} className="text-[10px]" title={l.value}>
              <span className="text-faint">
                {String(l.name).replace(/_/g, ' ')}
              </span>{' '}
              <span className="font-mono text-muted">{l.score}</span>
              {l.value ? (
                <span className="text-faint"> · {l.value}</span>
              ) : null}
            </span>
          ))}
        </div>
      )}

      {t.thesis && (
        <p className="pt-2 text-[11px] leading-relaxed text-muted">
          {t.thesis}
        </p>
      )}

      {Array.isArray(t.index?.top) && t.index.top.length > 0 && (
        <div className="pt-3">
          <div className="text-[9px] uppercase tracking-wider text-faint pb-1">
            quality index · {t.index.quality_n ?? '—'} names
            {t.index.pure_n != null && ` · pure ${t.index.pure_n}`}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1">
            {t.index.top.slice(0, 8).map((c) => (
              <div key={c.symbol} className="flex items-baseline justify-between font-mono text-[11px]">
                <span className="text-ink">
                  {c.symbol}
                  {c.role && (
                    <span className="ml-1 text-[8px] text-faint normal-case">
                      {c.role}
                    </span>
                  )}
                </span>
                <span className="text-faint">
                  {c.weight != null ? `${(c.weight * 100).toFixed(1)}%` : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* candidate pool — ranked, noted, never weighted. Promotion
          into the index is a decision, not a count to hit. */}
      {Array.isArray(t.pool) && t.pool.length > 0 && (
        <div className="pt-3 border-t border-hairline/60 mt-3">
          <div className="text-[9px] uppercase tracking-wider text-faint pb-1.5">
            candidate pool · {t.pool.length} watching
          </div>
          <div className="space-y-1">
            {t.pool.map((c) => (
              <div key={c.symbol}
                className="flex items-baseline gap-2 text-[10px]">
                <span className="font-mono text-ink w-14 shrink-0">
                  {c.symbol}
                </span>
                <span className="font-mono text-faint w-8 shrink-0">
                  {c.score ?? '—'}
                </span>
                {c.exposure && (
                  <span className={`rounded px-1 py-px text-[8px] uppercase tracking-wider shrink-0 ${
                    c.exposure === 'pure'
                      ? 'bg-constructive/15 text-constructive'
                      : c.exposure === 'speculative'
                        ? 'bg-caution/15 text-caution'
                        : 'bg-hairline/60 text-muted'
                  }`}>
                    {c.exposure}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-muted"
                  title={c.note}>
                  {c.note}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(t.missing) && t.missing.length > 0 && (
        <p className="pt-2 text-[10px] text-faint">
          missing: {t.missing.join(', ')}
        </p>
      )}
    </section>
  )
}

export default async function ThemesPage() {
  const data = await api.themeIntelligence()
  const today = data?.today
  const themes = today?.themes ?? {}
  const ranked = Object.entries(themes).sort(
    ([, a], [, b]) => (b.opportunity ?? -1) - (a.opportunity ?? -1),
  )

  return (
    <main className="mx-auto max-w-3xl px-5 pb-16 pt-6">
      <div className="flex items-baseline justify-between pb-4">
        <h1 className="text-lg font-semibold text-ink">
          Theme intelligence
        </h1>
        {today?.as_of && (
          <span className="font-mono text-[11px] text-faint">
            {today.as_of}
            {today.age_days != null && today.age_days > 0 &&
              ` · ${today.age_days}d old`}
          </span>
        )}
      </div>

      {today?.scenario_probs &&
        Object.keys(today.scenario_probs).length > 0 && (
          <section className="mb-4 rounded-xl border border-hairline bg-card px-5 py-3.5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-2">
              12-month scenario set
            </div>
            <ScenarioStrip probs={today.scenario_probs} />
          </section>
        )}

      {!today && (
        <p className="py-12 text-center text-sm text-faint">
          No theme snapshot yet — the weekly job hasn&apos;t run, or
          the journal is empty.
        </p>
      )}

      <div className="space-y-2">
        {ranked.map(([k, t]) => (
          <ThemeRow key={k} k={k} t={t} />
        ))}
      </div>

      <p className="pt-6 text-[10px] text-faint leading-relaxed">
        weekly · expected = scenario-probability × theme sensitivity —
        a disciplined ranking under uncertainty, not a return forecast
        · downside = stress-scenario fit only · robustness = 100 −
        probability-weighted dispersion · index weights: pure =
        exposure-tier, quality = constituent score, capped 6%/name
        · advisory — never an order
      </p>
    </main>
  )
}
