import { api, type ThemeCard } from '@/lib/api'
import Link from 'next/link'

export const dynamic = 'force-dynamic'

/** Custom ETF — the manage layer over Theme Intelligence. Each theme
 *  is a sleeve: quality-index constituents with weight + role +
 *  research stance (what the stock page would tell you to do), then
 *  the ranked candidate pool waiting for promotion. Advisory —
 *  balance is your call; the page shows where the sleeve and the
 *  stances disagree. */

function StanceChip({ stance }: { stance?: string | null }) {
  if (!stance) return <span className="text-faint">—</span>
  const tone =
    stance.includes('accumulate') || stance.includes('starter')
      ? 'bg-aggressive/15 text-aggressive'
      : stance.includes('trim') || stance.includes('exit')
        ? 'bg-defensive/15 text-defensive'
        : stance.includes('watch') || stance.includes('hold')
          ? 'bg-caution/15 text-caution'
          : 'bg-hairline/60 text-muted'
  return (
    <span className={`rounded-full px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider ${tone}`}>
      {stance.replace(/_/g, ' ').replace(' candidate', '')}
    </span>
  )
}

function EtfBlock({ k, t }: { k: string; t: ThemeCard }) {
  const rows = t.index?.top ?? []
  const pool = t.pool ?? []
  // stance-weight tension: where the index weight and the research
  // stance disagree — that's what a rebalance decision reads
  const friction = rows.filter(
    (r) =>
      (r.stance?.includes('trim') || r.stance?.includes('exit')) &&
      (r.weight ?? 0) >= 0.03,
  )
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <span className="text-[14px] font-semibold text-ink">
            {t.name ?? k}
          </span>
          <span className="ml-2 font-mono text-[11px] text-faint">
            {t.index?.quality_n ?? rows.length} names · opp{' '}
            {t.opportunity ?? '—'} · {(t.verdict ?? '—').replace(/_/g, ' ')}
          </span>
        </div>
        <Link
          href="/themes"
          className="text-[10px] text-faint hover:text-accent"
        >
          scorecard →
        </Link>
      </div>

      {friction.length > 0 && (
        <p className="pt-2 text-[10px] text-caution">
          tension: {friction.map((f) => f.symbol).join(', ')} — sized{' '}
          ≥3% while stance says{' '}
          {friction[0].stance?.replace(/_/g, ' ') ?? 'reduce'}
        </p>
      )}

      {/* constituents — the sleeve as it stands */}
      {rows.length > 0 && (
        <div className="pt-3">
          <div className="grid grid-cols-[3rem_3.5rem_1fr_6.5rem] sm:grid-cols-[3rem_3.5rem_1fr_8rem_6.5rem] gap-x-3 pb-1 text-[9px] uppercase tracking-wider text-faint">
            <span>sym</span>
            <span className="text-right">weight</span>
            <span className="hidden sm:block">role</span>
            <span>stance</span>
            <span className="hidden sm:block text-right">score</span>
          </div>
          {rows.map((r) => (
            <div key={r.symbol}
              className="grid grid-cols-[3rem_3.5rem_1fr_6.5rem] sm:grid-cols-[3rem_3.5rem_1fr_8rem_6.5rem] gap-x-3 items-baseline py-1 border-t border-hairline/40">
              <Link
                href={`/stock?sym=${encodeURIComponent(r.symbol ?? '')}`}
                className="font-mono text-[11px] text-ink hover:text-accent"
              >
                {r.symbol}
              </Link>
              <span className="font-mono text-[11px] text-muted text-right">
                {r.weight != null ? `${(r.weight * 100).toFixed(1)}%` : '—'}
              </span>
              <span className="hidden sm:block truncate text-[10px] text-faint">
                {r.role ?? ''}
              </span>
              <span>
                <StanceChip stance={r.stance} />
              </span>
              <span className="hidden sm:block font-mono text-[10px] text-faint text-right">
                {r.score ?? '—'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* pool — the bench, ranked with why-notes */}
      {pool.length > 0 && (
        <div className="pt-3 border-t border-hairline/60 mt-3">
          <div className="text-[9px] uppercase tracking-wider text-faint pb-1.5">
            bench · {pool.length} candidates — promote on evidence,
            not headcount
          </div>
          {pool.map((c) => (
            <div key={c.symbol}
              className="flex items-baseline gap-2 py-0.5 text-[10px]">
              <Link
                href={`/stock?sym=${encodeURIComponent(c.symbol ?? '')}`}
                className="font-mono text-ink w-14 shrink-0 hover:text-accent"
              >
                {c.symbol}
              </Link>
              <span className="font-mono text-faint w-8 shrink-0">
                {c.score ?? '—'}
              </span>
              <span className="hidden sm:block shrink-0">
                <StanceChip stance={c.stance} />
              </span>
              <span className="min-w-0 flex-1 truncate text-muted"
                title={c.note}>
                {c.note}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default async function EtfPage() {
  const data = await api.themeIntelligence()
  const today = data?.today
  const themes = today?.themes ?? {}
  const ranked = Object.entries(themes).sort(
    ([, a], [, b]) => (b.opportunity ?? -1) - (a.opportunity ?? -1),
  )

  return (
    <main className="mx-auto max-w-3xl px-5 pb-16 pt-6">
      <div className="flex items-baseline justify-between pb-4">
        <h1 className="text-lg font-semibold text-ink">Custom ETF</h1>
        {today?.as_of && (
          <span className="font-mono text-[11px] text-faint">
            {today.as_of}
            {today.age_days != null && today.age_days > 0 &&
              ` · ${today.age_days}d old`}
          </span>
        )}
      </div>

      {!today && (
        <p className="py-12 text-center text-sm text-faint">
          No theme snapshot yet — the weekly job hasn&apos;t run.
        </p>
      )}

      <div className="space-y-2">
        {ranked.map(([k, t]) => (
          <EtfBlock key={k} k={k} t={t} />
        ))}
      </div>

      <p className="pt-6 text-[10px] text-faint leading-relaxed">
        sleeves = quality-weighted index per theme, capped 6%/name ·
        stances come from weekly research runs — accumulate/watch/
        reduce are the stock page&apos;s own call, never an order ·
        tension flags size-vs-stance disagreement before you rebalance
        · bench names promote into the index on evidence, not headcount
      </p>
    </main>
  )
}
