import Link from 'next/link'
import { api, type MacroEvent, type EarningsRow } from '@/lib/api'
import { Section } from '@/components/regime'

function isoDay(d: Date) {
  return d.toISOString().slice(0, 10)
}

function fmtDay(d?: string) {
  if (!d) return '—'
  try {
    return new Date(d.length === 10 ? `${d}T12:00:00` : d)
      .toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric',
      })
  } catch {
    return d
  }
}

function pick(r: EarningsRow, keys: string[]) {
  for (const k of keys) {
    const v = r[k]
    if (v !== null && v !== undefined && v !== '') return v
  }
  return null
}

function MacroRow({ e }: { e: MacroEvent }) {
  const moved = e.rescheduled && e.rescheduled_from
  const isToday = e.days_away === 0
  const dateStr = e.when ?? e.date ?? ''
  const tag =
    e.days_away === 0 ? 'today'
      : e.days_away === 1 ? 'tomorrow'
        : e.days_away === -1 ? 'yesterday'
          : typeof e.days_away === 'number'
            ? e.days_away < 0 ? `${-e.days_away}d ago` : `in ${e.days_away}d`
            : ''
  const judge = e.judge
  const judgeTone =
    judge?.verdict === 'green' ? 'text-aggressive'
      : judge?.verdict === 'red' ? 'text-defensive'
        : judge?.verdict ? 'text-caution' : 'text-muted'
  return (
    <div className={`py-2.5 ${isToday ? 'border-l-2 border-accent pl-3' : ''}`}>
      <div className="flex justify-between gap-4 text-sm">
        <span className="text-ink">
          {e.title ?? e.name ?? 'event'}
          {e.unconfirmed && (
            <span className="text-caution"> ·?</span>
          )}
          {isToday && (
            <span className="ml-2 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent">
              today
            </span>
          )}
        </span>
        <span className="font-mono text-xs text-muted text-right shrink-0">
          {fmtDay(dateStr)}{tag && !isToday ? ` · ${tag}` : ''}
          {moved && (
            <span className="text-caution"> ⟵ was {e.rescheduled_from}</span>
          )}
        </span>
      </div>
      <div className="pt-0.5 text-xs text-muted space-y-0.5">
        {(e.actual != null || e.estimate != null) && (
          <div className="font-mono">
            {e.actual != null
              ? `printed ${e.actual}${e.estimate != null ? ` vs est ${e.estimate}` : ''}`
              : `est ${e.estimate}`}
            {e.prev != null && ` · prev ${e.prev}`}
          </div>
        )}
        {e.impact && <div>{e.impact}</div>}
        {e.reading && <div>{e.reading}</div>}
        {judge?.verdict && (
          <div className={judgeTone}>
            judge: {String(judge.verdict).toUpperCase()}
            {judge.confidence != null && ` (${judge.confidence}%)`}
            {judge.spy_ret != null &&
              ` · SPY ${(Number(judge.spy_ret) * 100).toFixed(2)}%`}
            {judge.thesis && ` — ${judge.thesis}`}
            {judge.correct === true && ' ✓'}
            {judge.correct === false && ' ✗'}
          </div>
        )}
        {e.source_url && (
          <div>
            <a
              className="underline underline-offset-2 text-faint hover:text-accent"
              href={String(e.source_url)}
              target="_blank"
              rel="noreferrer"
            >
              official release ↗
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

export default async function CalendarPage() {
  const now = new Date()
  const start = isoDay(now)
  const end = isoDay(new Date(now.getTime() + 14 * 86400000))
  const todayStr = start

  const [events, earnings] = await Promise.all([
    api.macroEvents(),
    api.earningsCalendar(start, end),
  ])

  const evList = Array.isArray(events) ? events : (events?.events ?? [])
  const erList = earnings?.data ?? []

  // group earnings by date
  const byDay = new Map<string, EarningsRow[]>()
  for (const r of erList) {
    const day = String(r.earnings_date ?? '').slice(0, 10)
    if (!day) continue
    byDay.set(day, [...(byDay.get(day) ?? []), r])
  }
  const days = [...byDay.keys()].sort()

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-8">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Today&apos;s calendar
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Earnings &amp; <span className="text-accent">Macro</span>
        </h1>
        <p className="pt-4 max-w-xl text-[15px] leading-relaxed text-muted">
          What prints on which day — earnings on the book&apos;s symbols plus
          the macro releases the regime engine watches.
        </p>
      </header>

      {/* earnings — grouped by day, today highlighted */}
      <Section title="Earnings" subtitle="next 14 days" defaultOpen>
        {days.length === 0 ? (
          <p className="text-sm text-muted">
            No earnings on the tracked book&apos;s calendar for the next two
            weeks.
          </p>
        ) : (
          <div className="space-y-4">
            {days.map((day) => {
              const isToday = day === todayStr
              return (
                <div key={day}>
                  <div
                    className={`pb-1.5 text-[11px] font-semibold uppercase tracking-wider ${isToday ? 'text-accent' : 'text-faint'
                      }`}
                  >
                    {fmtDay(day)}{isToday && ' — today'}
                  </div>
                  <div className={`space-y-1.5 ${isToday ? 'border-l-2 border-accent pl-3' : ''}`}>
                    {byDay.get(day)!.map((r, i) => {
                      const time = pick(r, ['time', 'session', 'timing', 'hour'])
                      const epsEst = pick(r, ['eps_estimate', 'eps_est', 'estimated_eps'])
                      const revEst = pick(r, ['revenue_estimate', 'rev_est'])
                      return (
                        <div
                          key={`${r.symbol}-${i}`}
                          className="flex items-baseline justify-between gap-4 text-sm"
                        >
                          <Link
                            href={`/stock?sym=${encodeURIComponent(String(r.symbol ?? ''))}`}
                            className="font-medium text-ink hover:text-accent transition-colors"
                          >
                            {String(r.symbol ?? '—')}
                          </Link>
                          <span className="font-mono text-xs text-muted text-right">
                            {time != null && `${String(time).toUpperCase()}`}
                            {epsEst != null && ` · EPS est ${String(epsEst)}`}
                            {revEst != null && ` · rev est ${String(revEst)}`}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {/* macro events — judge verdicts ride along */}
      <Section title="Macro events" subtitle="event-day judge verdicts" defaultOpen>
        {evList.length === 0 ? (
          <p className="text-sm text-muted">No macro events on the calendar.</p>
        ) : (
          <div className="divide-y divide-hairline/60">
            {evList.map((e, i) => <MacroRow key={i} e={e} />)}
          </div>
        )}
      </Section>

      <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
        advisory — scheduled events, not signals; today highlighted in orange
      </footer>
    </main>
  )
}
