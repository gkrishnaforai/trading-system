import Link from 'next/link'
import { api, type ReadinessRow } from '@/lib/api'
import { Chip } from '@/components/regime'

const LANES: [string, string][] = [
  ['swing', 'Swing'],
  ['invest', 'Invest'],
  ['leap_call', 'LEAP calls'],
  ['leap_put', 'LEAP puts'],
]

const STATE_TONE: Record<string, 'ok' | 'warn' | 'off'> = {
  ready: 'ok',
  close: 'warn',
  no: 'off',
}

// how much of each state bucket to render — 'ready' is the whole point
// so it never truncates; 'no' is context-only
const CAP: Record<string, number> = { ready: 999, close: 40, no: 15 }

function thesisMark(dir?: string | null) {
  if (dir === 'up') return <span className="text-aggressive">▲</span>
  if (dir === 'down') return <span className="text-defensive">▼</span>
  if (dir === 'flat') return <span className="text-muted">●</span>
  return null
}

function Row({ r, lane }: { r: ReadinessRow; lane: string }) {
  const fails = (r.fails ?? []) as string[]
  return (
    <div className="border-t border-hairline/60 py-2">
      <div className="flex items-center gap-2.5 min-w-0">
        <Link
          href={`/stock?sym=${encodeURIComponent(r.symbol)}`}
          className="font-semibold text-ink hover:text-accent transition-colors shrink-0"
        >
          {r.symbol}
        </Link>
        <span className="truncate text-[11px] text-faint">
          {r.name ?? ''}
        </span>
        <span className="ml-auto flex items-center gap-2 shrink-0 text-[10.5px] font-mono text-muted">
          {r.catalyst && (
            <span className="text-accent">{String(r.catalyst)}</span>
          )}
          {thesisMark(r.thesis_dir)}
          {r.mom && <span>{String(r.mom)}</span>}
          {r.fund && <span className="text-faint">{String(r.fund)}</span>}
          {r.fv_upside != null && (
            <span
              className={
                Number(r.fv_upside) > 0
                  ? 'text-aggressive'
                  : 'text-defensive'
              }
            >
              FV {Number(r.fv_upside) > 0 ? '+' : ''}
              {Number(r.fv_upside).toFixed(0)}%
            </span>
          )}
          {lane === 'swing' && r.swing_phase && (
            <span>{String(r.swing_phase)}</span>
          )}
          {r.rank != null && (
            <span className="text-ink font-semibold">
              {Number(r.rank).toFixed(0)}
            </span>
          )}
          {r.score != null && r.of != null && (
            <span className="text-faint">
              {Number(r.score)}/{Number(r.of)}
            </span>
          )}
        </span>
      </div>
      {fails.length > 0 && r.state !== 'no' && (
        <div className="pt-0.5 pl-1 text-[10.5px] text-faint">
          {fails.slice(0, 3).join(' · ')}
          {fails.length > 3 && ` · +${fails.length - 3}`}
        </div>
      )}
    </div>
  )
}

function StateGroup({
  label,
  rows,
  lane,
}: {
  label: string
  rows: ReadinessRow[]
  lane: string
}) {
  if (!rows.length) return null
  const cap = CAP[label] ?? 20
  const shown = rows.slice(0, cap)
  return (
    <div className="pt-3">
      <div className="flex items-baseline gap-2">
        <Chip label={`${label} ${rows.length}`} tone={STATE_TONE[label]} />
        {rows.length > cap && (
          <span className="text-[10px] text-faint">
            top {cap} by rank
          </span>
        )}
      </div>
      <div>
        {shown.map((r) => (
          <Row key={`${lane}-${r.symbol}`} r={r} lane={lane} />
        ))}
      </div>
    </div>
  )
}

export default async function ReadinessPage() {
  const d = await api.readiness()
  const sections = d?.sections ?? {}
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
        check passes, close is one or two away, no is gated. rank orders
        inside each state.
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

      {LANES.map(([key, label]) => {
        const rows = sections[key] ?? []
        if (!rows.length) return null
        const groups: Record<string, ReadinessRow[]> = {
          ready: [],
          close: [],
          no: [],
        }
        for (const r of rows) groups[r.state ?? 'no']?.push(r)
        return (
          <section key={key} className="mt-7">
            <div className="flex items-baseline justify-between border-b border-hairline pb-1.5">
              <h2 className="text-[12px] font-semibold uppercase tracking-[0.18em] text-ink">
                {label}
              </h2>
              <span className="text-[10.5px] font-mono text-faint">
                {rows.length} screened
              </span>
            </div>
            <StateGroup label="ready" rows={groups.ready} lane={key} />
            <StateGroup label="close" rows={groups.close} lane={key} />
            <StateGroup label="no" rows={groups.no} lane={key} />
          </section>
        )
      })}
    </main>
  )
}
