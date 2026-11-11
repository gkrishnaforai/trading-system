import { api, type ReadinessRow } from '@/lib/api'
import { ResilienceTable } from '@/components/resilience-table'
import { ReadinessBoard } from '@/components/readiness-board'

// how much of each state bucket ships to the client — 'ready' never
// truncates; 'no' is context-only
const CAP: Record<string, number> = { ready: 999, close: 40, no: 15 }

export default async function ReadinessPage() {
  const [d, states, pulse, tr] = await Promise.all([
    api.readiness(),
    api.readinessStates().catch(() => null),
    api.portfolioPulse().catch(() => null),
    api.transitions().catch(() => null),
  ])
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

      {/* actions today — the pulse's CURRENT call on every book name
          (holdings + watchlist): what to add, take profits on, cut, or
          leave alone. This is the trim/reduce + accumulate surface;
          the entry buckets below answer 'what can I open'. */}
      {pulse?.rows && (
        <section className="mt-4 rounded-lg border border-line/40 px-3 py-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            actions today
            <span className="ml-2 font-mono text-[10px] font-normal normal-case tracking-normal text-faint">
              book pulse{pulse.as_of ? ` · ${String(pulse.as_of).slice(0, 10)}` : ''}
            </span>
          </div>
          {([
            ['add', 'accumulate', 'border-aggressive/40 text-aggressive'],
            ['trim', 'trim — take profits', 'border-caution/40 text-caution'],
            ['reduce', 'reduce — cut', 'border-defensive/40 text-defensive'],
            ['avoid', 'avoid', 'border-hairline text-faint'],
          ] as const).map(([act, label, cls]) => {
            const rows = (pulse.rows ?? [])
              .filter((r) => r.action === act)
            if (!rows.length) return null
            return (
              <div key={act} className="pt-2">
                <div className="text-[10px] uppercase tracking-wider text-faint">
                  {label} ({rows.length})
                </div>
                <div className="flex flex-wrap gap-1 pt-1">
                  {rows.map((r) => (
                    <a
                      key={r.symbol}
                      href={`/stock?symbol=${r.symbol}`}
                      title={(Array.isArray(r.why)
                        ? r.why.join('; ') : r.why) ?? ''}
                      className={`rounded border px-1.5 py-px font-mono text-[11px] ${cls}`}
                    >
                      {r.symbol}
                    </a>
                  ))}
                </div>
              </div>
            )
          })}
          {(tr?.readiness?.length ?? 0) > 0 && (
            <div className="pt-2">
              <div className="text-[10px] uppercase tracking-wider text-faint">
                moved today — checklist state changes
              </div>
              <div className="flex flex-wrap gap-1 pt-1">
                {tr!.readiness!.map((r, i) => (
                  <a
                    key={`${r.symbol}-${r.use_case}-${i}`}
                    href={`/stock?symbol=${r.symbol}`}
                    title={`${r.use_case.replace(/_/g, ' ')}: ${r.prev_state} → ${r.state}`}
                    className={`rounded border px-1.5 py-px font-mono text-[11px] ${
                      r.state === 'ready'
                        ? 'border-aggressive/40 text-aggressive'
                        : r.state === 'no'
                          ? 'border-defensive/40 text-defensive'
                          : 'border-caution/40 text-caution'
                    }`}
                  >
                    {r.symbol}
                    <span className="text-faint">·{r.use_case === 'leap_call' ? 'lc' : r.use_case === 'leap_put' ? 'lp' : r.use_case === 'swing' ? 'sw' : 'inv'}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* entry lists — what you can OPEN by lane, all book symbols
          bucketed by the live checklist eval (not the journal), so a
          same-day heal or break shows now, not tomorrow. swing =
          short-hold timing, invest = fundamentals-led long hold,
          leap call/put = 12-18mo directional entries */}
      {useCases && (
        <section className="pt-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted pb-1">
            entry lists — ready to open by lane
          </div>
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
