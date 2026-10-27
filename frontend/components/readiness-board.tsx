'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { ReadinessRow } from '@/lib/api'

const LANES: [string, string][] = [
  ['swing', 'Swing'],
  ['invest', 'Invest'],
  ['leap_call', 'LEAP calls'],
  ['leap_put', 'LEAP puts'],
]

const STATES: [string, string][] = [
  ['ready', 'Ready'],
  ['close', 'Close'],
  ['no', 'No'],
]

const STATE_TEXT: Record<string, string> = {
  ready: 'text-aggressive',
  close: 'text-caution',
  no: 'text-muted',
}

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

export function ReadinessBoard({
  sections,
  counts,
}: {
  sections: Record<string, Record<string, ReadinessRow[]>>
  counts: Record<string, { ready?: number; close?: number; no?: number }>
}) {
  const [lane, setLane] = useState('swing')
  const [state, setState] = useState('ready')
  const groups = sections[lane] ?? { ready: [], close: [], no: [] }
  const laneCounts = counts[lane] ?? {}
  const shown = groups[state] ?? []
  const total = laneCounts[state as keyof typeof laneCounts] ?? shown.length
  const capped = total > shown.length

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-[11px] text-muted">
          lane
          <select
            value={lane}
            onChange={(e) => setLane(e.target.value)}
            className="rounded-md border border-hairline bg-card px-2.5 py-1.5 text-[12px] font-medium text-ink outline-none focus:border-accent"
          >
            {LANES.map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1">
          {STATES.map(([k, l]) => {
            const n = laneCounts[k as keyof typeof laneCounts] ?? 0
            const active = state === k
            return (
              <label
                key={k}
                className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-[11.5px] transition-colors ${active
                    ? 'border-accent bg-accent/10 text-ink'
                    : 'border-hairline text-muted hover:text-ink'
                  }`}
              >
                <input
                  type="radio"
                  name="readiness-state"
                  value={k}
                  checked={active}
                  onChange={() => setState(k)}
                  className="sr-only"
                />
                <span
                  className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-accent' : 'bg-faint/60'
                    }`}
                />
                {l}
                <span className="font-mono text-[10.5px] text-faint">
                  {n}
                </span>
              </label>
            )
          })}
        </div>
      </div>

      <div className="mt-2 flex items-baseline justify-between">
        <span className={`text-[11px] font-medium ${STATE_TEXT[state]}`}>
          {LANES.find(([k]) => k === lane)?.[1]} · {state}
          {capped && ` — top ${shown.length} of ${total} by rank`}
        </span>
      </div>

      {shown.length === 0 ? (
        <p className="pt-4 text-[12px] text-muted">
          nothing in this bucket.
        </p>
      ) : (
        <div>
          {shown.map((r) => (
            <Row key={`${lane}-${r.symbol}`} r={r} lane={lane} />
          ))}
        </div>
      )}
    </div>
  )
}
