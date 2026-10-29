import Link from 'next/link'
import { api, type ResearchRow } from '@/lib/api'
import { ResearchControls } from './controls'

export const dynamic = 'force-dynamic'

/** AI-tailwind research board — sector stocks ranked by journaled
 *  tailwind score, then best-product strength. Scores come from
 *  research_runs; unscored symbols sit at the bottom as
 *  'not researched' — never a false zero. */

function scoreTone(v?: number | null) {
  if (v == null) return 'text-faint'
  return v >= 70 ? 'text-aggressive' : v >= 50 ? 'text-caution' : 'text-defensive'
}

function RecChip({ rec }: { rec?: string | null }) {
  if (!rec) return null
  const tone = rec.includes('accumulate') || rec.includes('starter')
    ? 'bg-aggressive/15 text-aggressive'
    : rec.includes('exit') || rec.includes('trim')
      ? 'bg-defensive/15 text-defensive'
      : 'bg-caution/15 text-caution'
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tone}`}>
      {rec.replace(/_/g, ' ')}
    </span>
  )
}

function Row({ r, i }: { r: ResearchRow; i: number }) {
  const bp = r.best_product
  return (
    <div className="flex items-baseline gap-4 border-b border-hairline px-1 py-2.5 text-sm last:border-0">
      <span className="w-6 text-right font-mono text-[11px] text-faint">
        {i + 1}
      </span>
      <span className="min-w-0 flex-1">
        <Link
          href={`/stock?sym=${encodeURIComponent(r.symbol)}`}
          className="font-semibold text-ink hover:text-accent transition-colors"
        >
          {r.symbol}
        </Link>
        {r.name && (
          <span className="ml-2 truncate text-xs text-faint">{r.name}</span>
        )}
        {r.business_model && (
          <span className="ml-2 rounded bg-hairline/40 px-1.5 py-px text-[9.5px] uppercase tracking-wider text-faint">
            {String(r.business_model).replace(/_/g, ' ')}
          </span>
        )}
      </span>
      <span className="hidden min-w-[180px] max-w-[240px] truncate text-xs text-muted sm:block">
        {bp ? (
          <>
            <span className="text-ink">{bp.name}</span>
            <span className="text-faint">
              {' '}· {bp.stage}
              {bp.moats && bp.moats.length > 0 && ` · ${bp.moats.length} moat${bp.moats.length > 1 ? 's' : ''}`}
            </span>
          </>
        ) : (
          <span className="text-faint">—</span>
        )}
      </span>
      <span className={`w-12 text-right font-mono text-sm font-semibold ${scoreTone(r.ai_tailwind)}`}>
        {r.ai_tailwind != null ? Number(r.ai_tailwind).toFixed(0) : '—'}
      </span>
      <span className={`hidden w-12 text-right font-mono text-xs sm:block ${scoreTone(r.business_strength)}`}>
        {r.business_strength != null ? Number(r.business_strength).toFixed(0) : '—'}
      </span>
      <span className="w-32 text-right">
        {r.recommendation
          ? <RecChip rec={r.recommendation} />
          : <span className="text-[10px] text-faint">not researched</span>}
      </span>
    </div>
  )
}

export default async function ResearchPage() {
  const res = await api.researchBoard().catch(() => null)
  const rows = res?.rows ?? []
  const scored = rows.filter((r) => r.ai_tailwind != null)
  const unscored = rows.filter((r) => r.ai_tailwind == null)

  return (
    <main className="mx-auto max-w-4xl px-5 pb-20">
      <header className="pb-6 pt-6">
        <div className="pb-2 text-xs">
          <Link href="/board" className="text-faint hover:text-accent">
            ← board
          </Link>
        </div>
        <h1 className="font-semibold text-display text-ink">AI research</h1>
        <p className="pt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Healthcare names ranked by AI Tailwind Score — evidence that AI
          adoption creates durable economic value, then by strongest
          product (stage × moat breadth). A high score means tailwind
          exposure, not a cheap stock — the recommendation column is
          the gated decision.
        </p>
        <div className="pt-3 flex flex-wrap gap-x-6 gap-y-1 pb-3 text-[10px] uppercase tracking-[0.18em] text-faint">
          <span>{scored.length} scored</span>
          <span>{unscored.length} awaiting run</span>
          {scored[0]?.as_of && <span>latest {scored[0].as_of}</span>}
        </div>
        <ResearchControls />
      </header>

      {/* column headers */}
      <div className="flex items-baseline gap-4 px-1 pb-1 text-[10px] uppercase tracking-[0.18em] text-faint">
        <span className="w-6" />
        <span className="flex-1">company</span>
        <span className="hidden min-w-[180px] max-w-[240px] sm:block">best product</span>
        <span className="w-12 text-right">AI</span>
        <span className="hidden w-12 text-right sm:block">biz</span>
        <span className="w-32 text-right">stance</span>
      </div>

      <section className="rounded-xl border border-hairline bg-card px-3 py-1">
        {scored.map((r, i) => <Row key={r.symbol} r={r} i={i} />)}
        {scored.length === 0 && (
          <p className="px-1 py-6 text-sm text-faint">
            No research runs yet — trigger via POST /admin/research/{'{symbol}'}.
          </p>
        )}
      </section>

      {unscored.length > 0 && (
        <details className="mt-6">
          <summary className="cursor-pointer text-xs text-faint">
            {unscored.length} healthcare names not yet researched
          </summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {unscored.map((r) => (
              <Link
                key={r.symbol}
                href={`/stock?sym=${encodeURIComponent(r.symbol)}`}
                className="rounded border border-hairline px-2 py-1 text-xs text-muted hover:text-accent"
              >
                {r.symbol}
              </Link>
            ))}
          </div>
        </details>
      )}

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — deterministic scores, human decides</span>
        <span>research engine v1</span>
      </footer>
    </main>
  )
}
