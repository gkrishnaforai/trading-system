import { api } from '@/lib/api'
import { Chip, Kv, Section, Stat } from '@/components/regime'

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
  const [posture, morning, events] = await Promise.all([
    api.posture(),
    api.morningRegime(),
    api.macroEvents(),
  ])

  const p = posture ?? {}
  const today = morning?.today
  const record = morning?.record ?? []
  const evList = Array.isArray(events) ? events : (events?.events ?? [])

  const tone = TONE[p.posture ?? 'neutral'] ?? 'text-neutral'
  const label = LABEL[p.posture ?? 'neutral'] ?? 'Unknown'
  const asOf = p.regime_as_of || today?.as_of

  const buckets =
    today?.buckets && typeof today.buckets === 'object' && !Array.isArray(today.buckets)
      ? (today.buckets as Record<string, unknown>)
      : null

  const todayExtras = today
    ? Object.entries(today).filter(
      ([k]) =>
        !['as_of', 'regime', 'ai_regime', 'score', 'confidence',
          'buckets', 'verdict', 'horizon_1m', 'horizon_3m'].includes(k),
    )
    : []

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      {/* masthead */}
      <header className="flex items-baseline justify-between pt-8 pb-10">
        <span className="text-[13px] font-semibold tracking-[0.28em] text-muted">
          MARKETPULSE
        </span>
        <span className="font-mono text-xs text-faint">{fmtDate(asOf)}</span>
      </header>

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
            value={`${today.horizon_1m ?? '—'} · ${today.horizon_3m ?? '—'}`}
          />
        </section>
      )}

      {/* expandable depth */}
      <div className="mt-10">
        {buckets && (
          <Section title="What's driving it" subtitle="regime inputs">
            <div className="divide-y divide-transparent">
              {Object.entries(buckets).map(([k, v]) => (
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
                          {v === null || v === undefined
                            ? '—'
                            : typeof v === 'object'
                              ? JSON.stringify(v)
                              : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {evList.length > 0 && (
          <Section title="On the calendar" subtitle="macro events">
            <div className="divide-y divide-transparent">
              {evList.slice(0, 8).map((e, i) => (
                <Kv
                  key={i}
                  k={String(e.title ?? e.name ?? 'event')}
                  v={e.when ?? e.date ?? e.importance ?? ''}
                />
              ))}
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
          {today?.verdict ? String(today.verdict).slice(0, 40) : ''}
        </span>
      </footer>
    </main>
  )
}
