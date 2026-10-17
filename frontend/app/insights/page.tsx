import Link from 'next/link'
import { api } from '@/lib/api'
import { Section } from '@/components/regime'

export const dynamic = 'force-dynamic'

const KIND_CHIP: Record<string, string> = {
  daily_brief: 'border-accent/40 text-accent',
  receipts: 'border-aggressive/40 text-aggressive',
  event_verdict: 'border-caution/40 text-caution',
  mover: 'border-faint/40 text-muted',
  explainer: 'border-faint/40 text-muted',
}

const KIND_LABEL: Record<string, string> = {
  daily_brief: 'daily brief',
  receipts: 'receipts',
  event_verdict: 'event verdict',
  mover: 'mover',
  explainer: 'explainer',
}

export default async function InsightsPage() {
  const res = await api.posts({ limit: 60 })
  const posts = res?.posts ?? []
  return (
    <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
      <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-accent">
        Insights
      </p>
      <h1 className="mt-2 text-display font-semibold tracking-tight text-ink">
        Written by the ledger.
      </h1>
      <p className="mt-3 max-w-xl text-[14.5px] leading-relaxed text-muted">
        Every post is generated from journaled evidence — regime
        snapshots, graded picks, event verdicts — not a writer's hunch.
        The misses stay in.
      </p>

      <div className="mt-9 space-y-4">
        {posts.length === 0 && (
          <div className="rounded-lg border border-dashed border-hairline px-5 py-8 text-center text-[13px] text-faint">
            No posts yet — the daily brief publishes after the morning
            regime journals.
          </div>
        )}
        {posts.map((p) => (
          <Link
            key={p.slug}
            href={`/insights/${p.slug}`}
            className="group block rounded-xl border border-hairline bg-canvas px-5 py-4 transition-colors hover:border-accent/40"
          >
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider ${KIND_CHIP[p.kind] ?? 'border-faint/40 text-muted'}`}
              >
                {KIND_LABEL[p.kind] ?? p.kind}
              </span>
              <span className="font-mono text-[11.5px] text-faint">
                {p.as_of}
              </span>
            </div>
            <h2 className="mt-2 text-[16px] font-semibold tracking-tight text-ink group-hover:text-accent">
              {p.title}
            </h2>
            {p.dek && (
              <p className="mt-1 text-[13px] leading-relaxed text-muted">
                {p.dek}
              </p>
            )}
            {p.symbols && p.symbols.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {p.symbols.slice(0, 8).map((s) => (
                  <span
                    key={s}
                    className="rounded border border-hairline px-1.5 py-0.5 font-mono text-[11px] text-muted"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>

      <p className="mt-10 text-center text-[12px] text-faint">
        Advisory only. Deterministic evidence, human decides.
      </p>
    </main>
  )
}
