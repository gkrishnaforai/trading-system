import { api, type ReadinessRow } from '@/lib/api'
import { ReadinessBoard } from '@/components/readiness-board'

// how much of each state bucket ships to the client — 'ready' never
// truncates; 'no' is context-only
const CAP: Record<string, number> = { ready: 999, close: 40, no: 15 }

export default async function ReadinessPage() {
  const d = await api.readiness()
  const sections: Record<string, Record<string, ReadinessRow[]>> = {}
  for (const [lane, rows] of Object.entries(d?.sections ?? {})) {
    const groups: Record<string, ReadinessRow[]> = {
      ready: [], close: [], no: [],
    }
    for (const r of rows) groups[r.state ?? 'no']?.push(r)
    sections[lane] = {
      ready: groups.ready.slice(0, CAP.ready),
      close: groups.close.slice(0, CAP.close),
      no: groups.no.slice(0, CAP.no),
    }
  }
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

      {d && (
        <ReadinessBoard
          sections={sections}
          counts={d.counts ?? {}}
        />
      )}
    </main>
  )
}
