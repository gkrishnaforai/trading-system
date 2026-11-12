import { api } from '@/lib/api'
import { CycleTable } from '@/components/cycle-table'

export const dynamic = 'force-dynamic'

/** AI Cycle Rotation Tracker — quarterly business-cycle composite per
 *  name: 8 weighted evidence legs, three-peak detection (orders →
 *  estimates → revenue), demand-peak windows as ranges, and a policy
 *  decision per name. Seeded peak windows are priors (* = cohort seed)
 *  — claim-backed evidence overrides them. Decisions are postures,
 *  never orders: business quality stays separate from entry timing. */

const PHASE_TONE: Record<string, string> = {
  buildout: 'bg-caution/15 text-caution',
  deployment: 'bg-constructive/15 text-constructive',
  monetization: 'bg-aggressive/15 text-aggressive',
  efficiency: 'bg-hairline/60 text-muted',
}

const DEC_TONE: Record<string, string> = {
  accumulate: 'text-aggressive',
  add_on_pullback: 'text-constructive',
  hold: 'text-muted',
  trim: 'text-caution',
  exit: 'text-defensive',
  research_incomplete: 'text-faint',
}

const SPAN_LO = 2026
const SPAN_HI = 2032

function PeakBar({ lo, hi, conf }: {
  lo?: number; hi?: number; conf?: string | null
}) {
  if (!lo) return <div className="h-2 rounded bg-hairline/40" />
  const l = Math.max(0, Math.min(1, (lo - SPAN_LO) / (SPAN_HI - SPAN_LO)))
  const r = Math.max(l + 0.02,
    Math.min(1, ((hi ?? lo) - SPAN_LO) / (SPAN_HI - SPAN_LO)))
  const tone = conf === 'high' ? 'bg-defensive/70'
    : conf === 'medium' ? 'bg-caution/70' : 'bg-faint/50'
  return (
    <div className="relative h-2 rounded bg-hairline/40"
         title={`expected demand-peak window ${lo}–${hi ?? lo} (${conf ?? 'low'} confidence)`}>
      <div className={`absolute inset-y-0 rounded ${tone}`}
           style={{ left: `${l * 100}%`, right: `${(1 - r) * 100}%` }} />
    </div>
  )
}

export default async function CyclePage() {
  const d = await api.cycle()
  if (!d) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-lg font-semibold text-ink">
          AI Cycle Rotation
        </h1>
        <p className="mt-4 text-sm text-faint">worker unreachable</p>
      </main>
    )
  }
  const rows = d.rows ?? []
  const counts: Record<string, number> = {}
  for (const r of rows) {
    const k = r.decision ?? 'unknown'
    counts[k] = (counts[k] ?? 0) + 1
  }
  const cohorts = Object.entries(d.cohorts ?? {})
    .sort((a, b) => (b[1].median ?? 0) - (a[1].median ?? 0))

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h1 className="text-lg font-semibold text-ink">
          AI Cycle Rotation
        </h1>
        <span className="text-xs text-faint">
          {d.quarter_label ?? '—'} · as of {d.as_of ?? '—'} · {d.n ?? 0} names
        </span>
        <span className="flex gap-3 text-[11px] font-mono">
          {(['accumulate', 'add_on_pullback', 'hold', 'trim', 'exit',
             'research_incomplete'] as const).map(k =>
            counts[k] ? (
              <span key={k} className={DEC_TONE[k]}>
                {counts[k]} {k.replace(/_/g, ' ')}
              </span>
            ) : null)}
        </span>
      </header>

      {cohorts.length > 0 && (
        <section className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cohorts.map(([k, c]) => (
            <div key={k}
                 className="rounded-xl border border-hairline bg-card px-4 py-3">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[12px] font-semibold text-ink">
                  {c.label ?? k.replace(/_/g, ' ')}
                </span>
                {c.phase && (
                  <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${PHASE_TONE[c.phase] ?? 'bg-hairline/60 text-muted'}`}>
                    {c.phase}
                  </span>
                )}
              </div>
              <div className="mb-1.5 flex items-baseline justify-between text-[11px] text-faint">
                <span>{c.scored}/{c.n} scored
                  {c.median != null && ` · median ${c.median}`}</span>
                <span className="font-mono">
                  {c.peak?.lo
                    ? `peak ${c.peak.lo}–${c.peak.hi ?? c.peak.lo}`
                    : 'peak —'}
                </span>
              </div>
              <PeakBar lo={c.peak?.lo} hi={c.peak?.hi}
                       conf={c.peak?.confidence} />
              <div className="mt-1.5 flex flex-wrap gap-x-3 text-[10px] font-mono">
                {Object.entries(c.decisions ?? {}).map(([dec, n]) => (
                  <span key={dec} className={DEC_TONE[dec] ?? 'text-faint'}>
                    {n} {dec.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {rows.length === 0 ? (
        <div className="rounded-xl border border-hairline bg-card px-5 py-10 text-center text-sm text-faint">
          No cycle snapshots yet — the ai-cycle job journals the first
          weekly run.
        </div>
      ) : (
        <section className="rounded-xl border border-hairline bg-card px-4 py-3">
          <CycleTable rows={rows} />
          <p className="mt-3 text-[10px] text-faint">
            legs: dem demand · bkl backlog · rev revisions · mgn
            margin/cf · cap capacity · cus customers · fin financing ·
            val valuation — dots mark unknown legs (never zeroed).
            Peak dots: orders · estimates · revenue (red = rolled).
            * peak window is a cohort seed — a prior, not evidence.
          </p>
        </section>
      )}
    </main>
  )
}
