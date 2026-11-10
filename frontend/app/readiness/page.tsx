import { api, type ReadinessRow } from '@/lib/api'
import { ResilienceTable } from '@/components/resilience-table'
import { ReadinessBoard } from '@/components/readiness-board'

// how much of each state bucket ships to the client — 'ready' never
// truncates; 'no' is context-only
const CAP: Record<string, number> = { ready: 999, close: 40, no: 15 }

export default async function ReadinessPage() {
  const d = await api.readiness()
  const states = await api.readinessStates().catch(() => null)
  const sections: Record<string, Record<string, ReadinessRow[]>> = {}
  // live buckets from the just-computed sections — the checklist ran
  // on this request against the freshest engine detail, so chips move
  // the same day momentum_detail refreshes. The journaled
  // readiness-states view stays as the fallback only.
  const liveCases: Record<
    string,
    Record<string, { symbol: string; score: number | null;
                    rank: number | null }[]>
  > = {}
  for (const [lane, rows] of Object.entries(d?.sections ?? {})) {
    const groups: Record<string, ReadinessRow[]> = {
      ready: [], close: [], no: [],
    }
    const liveGroups: Record<string, { symbol: string;
        score: number | null; rank: number | null }[]> = {
      ready: [], close: [], no: [],
    }
    for (const r of rows) {
      groups[r.state ?? 'no']?.push(r)
      liveGroups[r.state ?? 'no']?.push(
        { symbol: r.symbol, score: r.score ?? null,
          rank: r.rank ?? null })
    }
    liveCases[lane] = liveGroups
    sections[lane] = {
      ready: groups.ready.slice(0, CAP.ready),
      close: groups.close.slice(0, CAP.close),
      no: groups.no.slice(0, CAP.no),
    }
  }
  const useCases = Object.keys(liveCases).length
    ? liveCases
    : states?.use_cases
  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-sm font-semibold tracking-[0.2em] uppercase text-ink">
          Readiness
        </h1>
        <span className="text-[11px] text-muted">
          {d?.as_of
            ? `engine data ${String(d.as_of).slice(0, 16)}`
            : 'no engine data journaled yet'}
        </span>
      </div>
      <p className="pt-1 text-[11px] text-muted">
        per-symbol checklists over stored engine data — ready means every
        check passes, close is one away, no is gated. rank orders inside
        each state.
      </p>

      {/* all book symbols bucketed by state — no truncation; the
          technical decision view (which names are ready vs close).
          Buckets come from this request's live checklist eval, so a
          same-day heal or break shows now, not tomorrow */}
      {useCases && (
        <section className="pt-4">
          {Object.entries(useCases).map(([uc, buckets]) => {
            const total = Object.values(buckets).reduce(
              (n, b) => n + b.length, 0)
            if (!total) return null
            return (
              <details key={uc} className="pb-3" open={uc === 'swing'}>
                <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {uc.replace(/_/g, ' ')} —{' '}
                  <span className="text-aggressive">{buckets.ready?.length ?? 0} ready</span> ·{' '}
                  <span className="text-caution">{buckets.close?.length ?? 0} close</span> ·{' '}
                  <span className="text-faint">{buckets.no?.length ?? 0} no</span>
                </summary>
                {(['ready', 'close', 'no'] as const).map((st) => {
                  const items = buckets[st] ?? []
                  if (!items.length) return null
                  return (
                    <div key={st} className="pt-2">
                      <div className={`text-[10px] uppercase tracking-wider ${
                        st === 'ready' ? 'text-aggressive' :
                        st === 'close' ? 'text-caution' : 'text-faint'}`}>
                        {st} ({items.length})
                      </div>
                      <div className="flex flex-wrap gap-1 pt-1">
                        {items.map((it) => (
                          <a key={it.symbol}
                             href={`/stock?symbol=${it.symbol}`}
                             className={`rounded border px-1.5 py-px font-mono text-[11px] ${
                               st === 'ready'
                                 ? 'border-aggressive/40 text-aggressive'
                                 : st === 'close'
                                   ? 'border-caution/40 text-caution'
                                   : 'border-hairline text-faint'}`}>
                            {it.symbol}
                          </a>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </details>
            )
          })}
        </section>
      )}

      {(d?.skipped?.length ?? 0) > 0 && (
        <div className="mt-3 rounded-lg border border-caution/40 bg-caution/5 px-3 py-2 text-[11px] text-caution">
          {d!.skipped!.length} symbol
          {d!.skipped!.length > 1 ? 's' : ''} skipped on corrupt stored
          data: {d!.skipped!.slice(0, 8).join(', ')}
          {d!.skipped!.length > 8 && '…'}
        </div>
      )}

      {!d && (
        <p className="pt-6 text-sm text-muted">
          readiness screen unavailable — worker unreachable.
        </p>
      )}

      {d && <ResilienceTable />}

      {d && (
        <ReadinessBoard
          sections={sections}
          counts={d.counts ?? {}}
        />
      )}
    </main>
  )
}
