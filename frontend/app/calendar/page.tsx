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

function fmtMoney(v: unknown) {
  const n = Number(v)
  if (!isFinite(n)) return null
  const a = Math.abs(n)
  if (a >= 1e12) return `$${(n / 1e12).toFixed(1)}T`
  if (a >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
  return `$${n}`
}

function relTag(daysAway: number | null | undefined, day: string, todayStr: string) {
  const d =
    typeof daysAway === 'number'
      ? daysAway
      : Math.round((Date.parse(`${day}T12:00:00Z`) - Date.parse(`${todayStr}T12:00:00Z`)) / 86400000)
  if (d === 0) return 'today'
  if (d === 1) return 'tomorrow'
  if (d === -1) return 'yesterday'
  return d < 0 ? `${-d}d ago` : `in ${d}d`
}

function pick(r: EarningsRow, keys: string[]) {
  for (const k of keys) {
    const v = r[k]
    if (v !== null && v !== undefined && v !== '') return v
  }
  return null
}

function timeChip(t?: string | null) {
  if (!t) return null
  const s = String(t).toLowerCase()
  if (s.includes('before')) return 'BMO'
  if (s.includes('after')) return 'AMC'
  return String(t)
}

function SevDot({ sev }: { sev?: string }) {
  const c =
    sev === 'extreme' ? 'bg-defensive'
      : sev === 'high' ? 'bg-caution'
        : 'bg-faint'
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${c}`} />
}

function EarningsLine({
  r,
  cap,
}: {
  r: EarningsRow
  cap?: { verdict?: string | null; drivers?: any[] } | null
}) {
  const verdict = cap?.verdict
  const drv = (cap?.drivers ?? []).find(
    (d) => d.delta_dir === 'cut' || d.delta_dir === 'raised',
  )
  const sym = String(r.symbol ?? '—')
  const name = pick(r, ['company_name', 'name'])
  const chip = timeChip(
    String(pick(r, ['earnings_time', 'time', 'session', 'timing', 'hour']) ?? ''),
  )
  const epsEst = pick(r, ['eps_estimate', 'eps_est', 'estimated_eps'])
  const revEst = pick(r, ['revenue_estimate', 'rev_est'])
  const epsAct = pick(r, ['eps_actual'])
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="min-w-0 truncate">
        <Link
          href={`/stock?sym=${encodeURIComponent(sym)}`}
          className="font-semibold text-ink hover:text-accent transition-colors"
        >
          {sym}
        </Link>
        {name && String(name) !== sym && (
          <span className="ml-2 text-xs text-faint">{String(name)}</span>
        )}
        {chip && (
          <span className={`ml-2 rounded-full px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wider ${chip === 'BMO' ? 'bg-caution/15 text-caution' : 'bg-accent/10 text-accent'}`}>
            {chip}
          </span>
        )}
        {verdict && (
          <span
            className={`ml-2 rounded-full border px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wider ${verdict === 'improving'
              ? 'border-aggressive/40 text-aggressive'
              : verdict === 'deteriorating'
                ? 'border-defensive/40 text-defensive'
                : 'border-caution/40 text-caution'
              }`}
          >
            {verdict}
          </span>
        )}
        {drv && (
          <span
            className={`ml-2 rounded-full px-1.5 py-px text-[9.5px] font-semibold ${drv.delta_dir === 'raised'
              ? 'bg-aggressive/15 text-aggressive'
              : 'bg-defensive/15 text-defensive'
              }`}
            title={`${drv.metric} ${drv.period}: ${drv.value_text ?? ''}`}
          >
            {String(drv.metric).replace(/_/g, ' ')}{' '}
            {drv.delta_dir === 'raised' ? '↑' : '↓'}
            {drv.delta_pct != null &&
              `${Math.abs(Number(drv.delta_pct) * 100).toFixed(0)}%`}
          </span>
        )}
      </span>
      <span className="shrink-0 text-right font-mono text-xs text-muted">
        {epsAct != null
          ? `EPS ${String(epsAct)}${epsEst != null ? ` vs ${String(epsEst)}` : ''}`
          : epsEst != null && `EPS est ${String(epsEst)}`}
        {revEst != null && fmtMoney(revEst) && ` · rev est ${fmtMoney(revEst)}`}
      </span>
    </div>
  )
}

function MacroLine({ e, detailed }: { e: MacroEvent; detailed?: boolean }) {
  const judge = e.judge
  const judgeTone =
    judge?.verdict === 'green' ? 'text-aggressive'
      : judge?.verdict === 'red' ? 'text-defensive'
        : 'text-caution'
  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="flex min-w-0 items-center gap-2 text-ink">
          <SevDot sev={String(e.severity ?? '')} />
          <span className="truncate">
            {e.title ?? e.name ?? 'event'}
            {e.unconfirmed && <span className="text-caution"> ·?</span>}
          </span>
        </span>
        <span className="shrink-0 font-mono text-xs text-muted">
          {e.time_et ? <span className="text-faint">{String(e.time_et)} ET · </span> : null}
          {e.actual != null
            ? `printed ${e.actual}${e.estimate != null ? ` vs est ${e.estimate}` : ''}`
            : e.estimate != null && `est ${e.estimate}`}
          {e.prev != null && ` · prev ${e.prev}`}
        </span>
      </div>
      {detailed && (
        <div className="space-y-0.5 pl-3.5 pt-0.5 text-xs text-muted">
          {e.rescheduled && e.rescheduled_from && (
            <div className="text-caution">rescheduled — was {e.rescheduled_from}</div>
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
                className="text-faint underline underline-offset-2 hover:text-accent"
                href={String(e.source_url)}
                target="_blank"
                rel="noreferrer"
              >
                official release ↗
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default async function CalendarPage() {
  const now = new Date()
  const todayStr = isoDay(now)
  const end = isoDay(new Date(now.getTime() + 14 * 86400000))

  const [events, earnings, watch] = await Promise.all([
    api.macroEvents(),
    api.earningsCalendar(todayStr, end),
    api.earningsWatch(30),
  ])

  const evList = Array.isArray(events) ? events : (events?.events ?? [])
  const erList = earnings?.data ?? []
  const verdicts = new Map<
    string, { verdict?: string | null; drivers?: any[] }>()
  for (const c of watch?.captures ?? []) {
    verdicts.set(`${c.symbol}|${String(c.earnings_date).slice(0, 10)}`, {
      verdict: c.verdict,
      drivers: (c as any)?.detail?.drivers,
    })
  }
  const verdictFor = (r: EarningsRow) =>
    verdicts.get(
      `${r.symbol}|${String(r.earnings_date ?? '').slice(0, 10)}`,
    ) ?? null

  const earnByDay = new Map<string, EarningsRow[]>()
  for (const r of erList) {
    const day = String(r.earnings_date ?? '').slice(0, 10)
    if (!day) continue
    earnByDay.set(day, [...(earnByDay.get(day) ?? []), r])
  }
  const macroByDay = new Map<string, MacroEvent[]>()
  for (const e of evList) {
    const day = String(e.date ?? e.when ?? '').slice(0, 10)
    if (!day) continue
    macroByDay.set(day, [...(macroByDay.get(day) ?? []), e])
  }

  // this week — Mon→Sun strip
  const dow = (now.getUTCDay() + 6) % 7
  const weekStart = new Date(now.getTime() - dow * 86400000)
  const week = Array.from({ length: 7 }, (_, i) =>
    isoDay(new Date(weekStart.getTime() + i * 86400000)),
  )

  // upcoming days = union of earnings + macro days >= today, sorted
  const upcoming = [...new Set([...earnByDay.keys(), ...macroByDay.keys()])]
    .filter((d) => d >= todayStr && d <= end)
    .sort()
  const future = upcoming.filter((d) => d > todayStr)
  const prints = evList
    .filter((e) => typeof e.days_away === 'number' && e.days_away < 0)
    .sort((a, b) => (b.days_away ?? 0) - (a.days_away ?? 0))
    .slice(0, 10)

  const todayEarn = earnByDay.get(todayStr) ?? []
  const todayMacro = macroByDay.get(todayStr) ?? []
  const todayEmpty = todayEarn.length === 0 && todayMacro.length === 0
  const nextDay = future[0]
  const weekend = now.getUTCDay() === 0 || now.getUTCDay() === 6

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-6">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Earnings hub
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Earnings &amp; <span className="text-accent">Macro</span>
        </h1>
      </header>

      {/* this week — strip */}
      <section className="grid grid-cols-7 gap-1 pb-8">
        {week.map((d) => {
          const isToday = d === todayStr
          const nEarn = earnByDay.get(d)?.length ?? 0
          const macros = macroByDay.get(d) ?? []
          const worst = macros.some((m) => m.severity === 'extreme')
            ? 'extreme'
            : macros.some((m) => m.severity === 'high') ? 'high' : null
          const isWknd = [5, 6].includes(week.indexOf(d))
          return (
            <div
              key={d}
              className={`rounded-lg border px-1.5 py-2 text-center ${isToday
                ? 'border-accent bg-accent/5'
                : 'border-hairline'
                } ${isWknd ? 'opacity-45' : ''}`}
            >
              <div className="text-[10px] font-medium uppercase tracking-wider text-faint">
                {new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short' })}
              </div>
              <div className={`font-mono text-sm ${isToday ? 'font-semibold text-accent' : 'text-ink'}`}>
                {Number(d.slice(8))}
              </div>
              <div className="flex h-3.5 items-center justify-center gap-1 pt-0.5">
                {nEarn > 0 && (
                  <span className="rounded-full bg-accent/15 px-1 text-[9px] font-semibold text-accent">
                    {nEarn}
                  </span>
                )}
                {worst && <SevDot sev={worst} />}
              </div>
            </div>
          )
        })}
      </section>

      {/* today — the focus card */}
      <section className="rounded-xl border border-hairline bg-elevated p-5">
        <div className="flex items-baseline justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-accent">
            Today — {fmtDay(todayStr)}
          </div>
          {!todayEmpty && (
            <div className="font-mono text-xs text-faint">
              {todayEarn.length > 0 && `${todayEarn.length} earnings`}
              {todayEarn.length > 0 && todayMacro.length > 0 && ' · '}
              {todayMacro.length > 0 && `${todayMacro.length} macro`}
            </div>
          )}
        </div>
        {todayEmpty ? (
          <div className="pt-4">
            <p className="text-sm text-muted">
              {weekend
                ? 'Weekend — markets are closed. Nothing scheduled.'
                : 'Nothing on the tape today.'}
            </p>
            {nextDay && (
              <p className="pt-2 text-xs text-faint">
                Next up: {fmtDay(nextDay)} ({relTag(null, nextDay, todayStr)})
                {earnByDay.get(nextDay)?.length
                  ? ` — ${earnByDay.get(nextDay)!.map((r) => String(r.symbol)).join(', ')}`
                  : macroByDay.get(nextDay)?.length
                    ? ` — ${macroByDay.get(nextDay)!.map((e) => e.title ?? e.name).join(', ')}`
                    : ''}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1 pt-4">
            {todayMacro.map((e, i) => <MacroLine key={i} e={e} detailed />)}
            {todayEarn.map((r, i) => (
              <EarningsLine key={i} r={r} cap={verdictFor(r)} />
            ))}
          </div>
        )}
      </section>

      {/* upcoming — merged day-by-day */}
      <Section title="Next up" subtitle="next 14 days" defaultOpen>
        {future.length === 0 ? (
          <p className="text-sm text-muted">
            Nothing scheduled on the book&apos;s calendar for the next two
            weeks.
          </p>
        ) : (
          <div className="space-y-5">
            {future.map((day) => {
              const macros = macroByDay.get(day) ?? []
              const earns = earnByDay.get(day) ?? []
              const extreme = macros.some((m) => m.severity === 'extreme')
              return (
                <div key={day}>
                  <div className="flex items-baseline gap-3 pb-2">
                    <span className={`text-[11px] font-semibold uppercase tracking-wider ${extreme ? 'text-defensive' : 'text-faint'}`}>
                      {fmtDay(day)}
                    </span>
                    <span className="font-mono text-[10px] text-faint">
                      {relTag(null, day, todayStr)}
                    </span>
                  </div>
                  <div className={`space-y-1 ${extreme ? 'border-l-2 border-defensive/60 pl-3' : ''}`}>
                    {macros.map((e, i) => <MacroLine key={i} e={e} detailed />)}
                    {earns.map((r, i) => (
                      <EarningsLine key={i} r={r} cap={verdictFor(r)} />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {/* recent prints — judged receipts */}
      <Section title="Recent prints" subtitle="what already landed" defaultOpen={false}>
        {prints.length === 0 ? (
          <p className="text-sm text-muted">No recent prints on record.</p>
        ) : (
          <div className="divide-y divide-hairline/60">
            {prints.map((e, i) => (
              <div key={i}>
                <div className="pt-1 font-mono text-[10px] uppercase tracking-wider text-faint">
                  {fmtDay(e.date ?? e.when ?? '')} · {relTag(e.days_away, String(e.date ?? ''), todayStr)}
                </div>
                <MacroLine e={e} detailed />
              </div>
            ))}
          </div>
        )}
      </Section>

      <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
        advisory — scheduled events, not signals; dots mark macro severity
        (red extreme · yellow high), numbers mark earnings count
      </footer>
    </main>
  )
}
