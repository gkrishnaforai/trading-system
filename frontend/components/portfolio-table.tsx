'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import type { PulseRow } from '@/lib/api'

// bump when new default-on columns ship — a stale saved list would
// hide columns the user never chose to remove
const LS_KEY = 'pf_table_cols_v2'

const BUCKET_ORDER = [
  'reduce', 'trim', 'avoid', 'attention', 'add', 'stalk', 'hold',
]
const BUCKET_LABEL: Record<string, string> = {
  reduce: 'Reduce', trim: 'Trim', avoid: 'Avoid',
  attention: 'Attention', add: 'Add', stalk: 'Stalk', hold: 'Hold',
}
const BUCKET_TONE: Record<string, string> = {
  reduce: 'text-defensive border-defensive/30 bg-defensive/10',
  trim: 'text-caution border-caution/30 bg-caution/10',
  avoid: 'text-defensive border-defensive/30 bg-defensive/10',
  attention: 'text-caution border-caution/30 bg-caution/10',
  add: 'text-aggressive border-aggressive/30 bg-aggressive/10',
  stalk: 'text-constructive border-constructive/30 bg-constructive/10',
  hold: 'text-muted border-hairline bg-elevated/60',
}
// the policy's call as a directional glyph — ▲ build / ▽▼ cut risk /
// ◆ hold/watch — the label stays, the icon scans
const BUCKET_GLYPH: Record<string, string> = {
  reduce: '▼', trim: '▽', avoid: '✕',
  attention: '⚑', add: '▲', stalk: '◐', hold: '◆',
}

function money(v?: number | null, dec = 2) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return `$${Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })}`
}
function num(v?: number | null, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })
}
function pct(v?: number | null, sign = true, dec = 1) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  const n = Number(v)
  return `${sign && n >= 0 ? '+' : ''}${n.toFixed(dec)}%`
}
function tone(v?: number | null) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 0 ? 'text-aggressive' : 'text-defensive'
}

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (!data || data.length < 2)
    return <span className="text-faint">—</span>
  const w = 72, h = 22, pad = 1.5
  const lo = Math.min(...data), hi = Math.max(...data)
  const span = hi - lo || 1
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2)
    const y = pad + (1 - (v - lo) / span) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const last = data[data.length - 1]
  const lx = w - pad
  const ly = pad + (1 - (last - lo) / span) * (h - pad * 2)
  const c = up ? '#15803D' : '#B91C1C'
  return (
    <svg width={w} height={h} className="block" aria-hidden>
      <polyline
        points={pts} fill="none" stroke={c}
        strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round"
        opacity="0.8"
      />
      <circle cx={lx} cy={ly} r="1.8" fill={c} />
    </svg>
  )
}

type ColKey =
  | 'spark' | 'price' | 'day' | 'dayd' | 'shares' | 'avg' | 'cost'
  | 'value' | 'pnlp' | 'pnld' | 'wt' | 'fv' | 'mom' | 'fund'
  | 'rev' | 'earn' | 'qtr0' | 'qtr1' | 'qtr2' | 'traj'

type Col = {
  key: ColKey
  label: string
  title: string
  on: boolean                    // default visible
  sort?: (r: PulseRow) => number | null
  cell: (r: PulseRow, ctx: Ctx) => React.ReactNode
}

type Ctx = { bookValue: number }

const posValue = (r: PulseRow) => (r.shares ?? 0) * (r.price ?? 0)
const posCost = (r: PulseRow) => (r.shares ?? 0) * (r.avg_cost ?? 0)
const posPnl$ = (r: PulseRow) =>
  r.price && r.avg_cost ? posValue(r) - posCost(r) : null
const posDay$ = (r: PulseRow) =>
  r.price && r.prev_close
    ? (r.shares ?? 0) * (Number(r.price) - Number(r.prev_close))
    : null

const COLS: Col[] = [
  {
    key: 'spark', label: '30d', title: 'last 30 daily closes',
    on: true,
    sort: (r) => {
      const s = r.spark ?? []
      return s.length > 1 && s[0]
        ? (s[s.length - 1] / s[0] - 1) * 100 : null
    },
    cell: (r) => {
      const s = r.spark ?? []
      const up = s.length > 1 && s[s.length - 1] >= s[0]
      return <Spark data={s} up={up} />
    },
  },
  {
    key: 'price', label: 'Price', title: 'last close',
    on: true, sort: (r) => r.price ?? null,
    cell: (r) => <span className="text-ink">{money(r.price)}</span>,
  },
  {
    key: 'day', label: 'Day', title: 'change vs previous close',
    on: true, sort: (r) => r.day_chg_pct ?? null,
    cell: (r) => (
      <span className={tone(r.day_chg_pct)}>
        {pct(r.day_chg_pct, true, 2)}
      </span>
    ),
  },
  {
    key: 'dayd', label: 'Day $', title: 'today\u2019s P/L in dollars',
    on: false, sort: (r) => posDay$(r),
    cell: (r) => (
      <span className={tone(posDay$(r))}>{money(posDay$(r), 0)}</span>
    ),
  },
  {
    key: 'shares', label: 'Shares', title: 'quantity held',
    on: true, sort: (r) => r.shares ?? null,
    cell: (r) => <span className="text-ink">{num(r.shares)}</span>,
  },
  {
    key: 'avg', label: 'Avg cost', title: 'average cost basis',
    on: true, sort: (r) => r.avg_cost ?? null,
    cell: (r) => money(r.avg_cost),
  },
  {
    key: 'cost', label: 'Cost', title: 'total cost basis',
    on: false, sort: (r) => posCost(r) || null,
    cell: (r) => money(posCost(r), 0),
  },
  {
    key: 'value', label: 'Mkt value', title: 'current market value',
    on: true, sort: (r) => posValue(r) || null,
    cell: (r) => (
      <span className="text-ink">{money(posValue(r), 0)}</span>
    ),
  },
  {
    key: 'pnlp', label: 'P/L %', title: 'unrealized gain vs cost',
    on: true, sort: (r) => r.pnl_pct ?? null,
    cell: (r) => (
      <span className={tone(r.pnl_pct)}>{pct(r.pnl_pct)}</span>
    ),
  },
  {
    key: 'pnld', label: 'P/L $', title: 'unrealized gain in dollars',
    on: true, sort: (r) => posPnl$(r),
    cell: (r) => (
      <span className={tone(posPnl$(r))}>{money(posPnl$(r), 0)}</span>
    ),
  },
  {
    key: 'wt', label: 'Weight', title: 'share of book value',
    on: true,
    sort: (r) => null, // ctx-dependent; handled in comparator
    cell: (r, ctx) => {
      const w = ctx.bookValue > 0
        ? (posValue(r) / ctx.bookValue) * 100 : null
      if (w == null) return '—'
      return (
        <span className="inline-flex items-center gap-1.5">
          <span className="text-muted">{w.toFixed(1)}%</span>
          <span className="h-1 w-8 rounded-full bg-elevated overflow-hidden">
            <span
              className="block h-full rounded-full bg-accent/70"
              style={{ width: `${Math.min(w, 100)}%` }}
            />
          </span>
        </span>
      )
    },
  },
  {
    key: 'fv', label: 'FV gap', title: 'fair-value upside',
    on: false, sort: (r) => r.fv_upside ?? null,
    cell: (r) => (
      <span className={tone(r.fv_upside)}>{pct(r.fv_upside)}</span>
    ),
  },
  {
    key: 'mom', label: 'Tape', title: 'momentum state',
    on: false, cell: (r) => (
      <span className="text-muted">
        {r.mom_state ? String(r.mom_state).replace(/_/g, ' ') : '—'}
      </span>
    ),
  },
  {
    key: 'fund', label: 'Fund', title: 'fundamental state',
    on: false, cell: (r) => <span className="text-muted">{r.fund_state ?? '—'}</span>,
  },
  {
    key: 'rev', label: 'Rev', title: 'estimate-revision grade',
    on: false, cell: (r) => <span className="text-muted">{r.revision_grade ?? '—'}</span>,
  },
  // ---- last-3 quarterly prints: journaled surprise % per quarter,
  // verdict overlay where the watcher covered it (▲ improving /
  // ▼ deteriorating / · pending) — evidence, not a score ----
  ...([0, 1, 2] as const).map((qi): Col => ({
    key: (`qtr${qi}` as ColKey),
    label: `Q-${qi + 1}`,
    title: `quarterly print ${qi + 1} back — surprise %, verdict ▲/▼ when journaled`,
    on: true,
    sort: (r) => r.quarters?.[qi]?.surp ?? null,
    cell: (r) => {
      const q = r.quarters?.[qi]
      if (!q) return <span className="text-faint">—</span>
      const s = q.surp
      const cls = s == null ? 'text-muted'
        : s > 0 ? 'text-aggressive'
          : s < 0 ? 'text-defensive' : 'text-muted'
      const vd = q.verdict === 'improving' ? '▲'
        : q.verdict === 'deteriorating' ? '▼'
          : q.verdict === 'mixed' ? '◆' : ''
      return (
        <span
          className={cls}
          title={`${q.d}${q.verdict ? ` · ${q.verdict}` : ''}`}
        >
          {s == null ? '·' : `${s > 0 ? '+' : ''}${s.toFixed(0)}`}
          {vd && <span className="text-[9px]">{vd}</span>}
        </span>
      )
    },
  })),
  {
    key: 'traj', label: 'Traj', title:
      'earnings trajectory — majority of last-3 journaled print verdicts; ' +
      '▲ improving / ▼ deteriorating / ◆ mixed / · insufficient · ' +
      'feeds the action engine (deteriorating blocks adds)',
    on: true,
    cell: (r) => {
      const t = r.earn_traj
      const g = t === 'improving' ? ['▲', 'text-aggressive']
        : t === 'deteriorating' ? ['▼', 'text-defensive']
          : t === 'mixed' ? ['◆', 'text-caution']
            : ['·', 'text-faint']
      return (
        <span className={g[1]} title={t ?? 'insufficient'}>
          {g[0]}
          {(r.eq_flags ?? []).length > 0 && (
            <span
              className="ml-0.5 text-defensive"
              title={String(r.eq_flags!.join(', '))}
            >
              ⚑
            </span>
          )}
        </span>
      )
    },
  },
  {
    key: 'earn', label: 'Earnings', title: 'next earnings date',
    on: false, sort: (r) => r.next_earnings_date
      ? Date.parse(r.next_earnings_date) : null,
    cell: (r) => (
      <span className="text-muted">
        {r.next_earnings_date
          ? new Date(r.next_earnings_date).toLocaleDateString('en-US',
            { month: 'short', day: 'numeric' })
          : '—'}
      </span>
    ),
  },
]

export function PortfolioTable({ rows, bookValue }: {
  rows: PulseRow[]
  bookValue: number
}) {
  const [cols, setCols] = useState<ColKey[] | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [sortKey, setSortKey] = useState<ColKey | null>(null)
  const [sortDir, setSortDir] = useState<1 | -1>(-1)
  const [bucketFilter, setBucketFilter] = useState<string | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const pickerRef = useRef<HTMLDivElement>(null)

  // load persisted columns after mount (SSR-safe)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY)
      setCols(raw ? JSON.parse(raw) : COLS.filter((c) => c.on).map((c) => c.key))
    } catch {
      setCols(COLS.filter((c) => c.on).map((c) => c.key))
    }
  }, [])

  useEffect(() => {
    if (!pickerOpen) return
    const onDoc = (e: MouseEvent) => {
      if (!pickerRef.current?.contains(e.target as Node))
        setPickerOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [pickerOpen])

  const visible = useMemo(
    () => COLS.filter((c) => cols?.includes(c.key) ?? c.on),
    [cols],
  )

  const bucketCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of rows)
      m.set(String(r.bucket), (m.get(String(r.bucket)) ?? 0) + 1)
    return m
  }, [rows])

  const filtered = useMemo(
    () => bucketFilter
      ? rows.filter((r) => String(r.bucket) === bucketFilter)
      : rows,
    [rows, bucketFilter],
  )

  const sorted = useMemo(() => {
    const ctx: Ctx = { bookValue }
    if (!sortKey) return filtered
    const col = COLS.find((c) => c.key === sortKey)
    const sorter = col?.sort
    if (!sorter) return filtered
    const score = (r: PulseRow) =>
      sortKey === 'wt' && bookValue > 0
        ? (posValue(r) / bookValue) * 100
        : sorter(r)
    return [...filtered].sort((a, b) => {
      const av = score(a), bv = score(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return (av - bv) * sortDir
    })
  }, [filtered, sortKey, sortDir, bookValue])

  const toggleSort = (k: ColKey) => {
    const col = COLS.find((c) => c.key === k)
    if (!col?.sort) return
    if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1))
    else { setSortKey(k); setSortDir(-1) }
  }

  const toggleCol = (k: ColKey) => {
    setCols((cur) => {
      const base = cur ?? COLS.filter((c) => c.on).map((c) => c.key)
      const next = base.includes(k)
        ? base.filter((x) => x !== k)
        : [...base, k]
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)) }
      catch { /* private mode */ }
      return next
    })
  }

  const toggleRow = (sym: string) =>
    setOpen((s) => {
      const n = new Set(s)
      n.has(sym) ? n.delete(sym) : n.add(sym)
      return n
    })

  const totals = useMemo(() => {
    const ps = sorted.filter((r) => r.kind === 'position')
    return {
      cost: ps.reduce((a, r) => a + posCost(r), 0),
      value: ps.reduce((a, r) => a + posValue(r), 0),
      pnl: ps.reduce((a, r) => a + (posPnl$(r) ?? 0), 0),
      day: ps.reduce((a, r) => a + (posDay$(r) ?? 0), 0),
    }
  }, [sorted])

  const cellCls =
    'px-3 py-2.5 font-mono text-xs text-muted whitespace-nowrap'
  const headCls =
    'px-3 py-2 text-left font-sans text-[10px] font-medium ' +
    'uppercase tracking-wider text-faint whitespace-nowrap select-none'

  return (
    <div>
      {/* ---- control strip: bucket filters + column picker ---- */}
      <div className="flex flex-wrap items-center gap-1.5 pb-3">
        <button
          onClick={() => setBucketFilter(null)}
          className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${bucketFilter === null
            ? 'border-ink/30 bg-ink text-canvas'
            : 'border-hairline text-muted hover:border-ink/20'
            }`}
        >
          All <span className="font-mono">{rows.length}</span>
        </button>
        {BUCKET_ORDER.filter((b) => bucketCounts.get(b)).map((b) => (
          <button
            key={b}
            onClick={() =>
              setBucketFilter((f) => (f === b ? null : b))}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${bucketFilter === b
              ? BUCKET_TONE[b]
              : 'border-hairline text-muted hover:border-ink/20'
              }`}
          >
            {BUCKET_LABEL[b]}{' '}
            <span className="font-mono">{bucketCounts.get(b)}</span>
          </button>
        ))}
        <div className="ml-auto relative" ref={pickerRef}>
          <button
            onClick={() => setPickerOpen((o) => !o)}
            className="rounded-full border border-hairline px-2.5 py-1 text-[11px] text-muted hover:border-ink/20 transition-colors"
          >
            Columns <span className="font-mono">{visible.length}</span> ▾
          </button>
          {pickerOpen && (
            <div className="absolute right-0 z-20 mt-1.5 w-44 rounded-xl border border-hairline bg-card p-2 shadow-[0_8px_30px_-12px_rgba(13,12,10,0.25)]">
              {COLS.map((c) => (
                <label
                  key={c.key}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs text-ink hover:bg-elevated/70"
                  title={c.title}
                >
                  <input
                    type="checkbox"
                    checked={cols?.includes(c.key) ?? c.on}
                    onChange={() => toggleCol(c.key)}
                    className="h-3.5 w-3.5 accent-[#EA580C]"
                  />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ---- the grid ---- */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-hairline">
              <th className={headCls}>Symbol</th>
              {visible.map((c) => (
                <th
                  key={c.key}
                  className={`${headCls} text-right ${c.sort ? 'cursor-pointer hover:text-ink' : ''
                    }`}
                  title={c.title + (c.sort ? ' · click to sort' : '')}
                  onClick={() => toggleSort(c.key)}
                >
                  {c.label}
                  {sortKey === c.key && (
                    <span className="text-accent">
                      {sortDir === 1 ? ' ↑' : ' ↓'}
                    </span>
                  )}
                </th>
              ))}
              <th className={`${headCls} text-right`}>Action</th>
              <th className="w-6" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const sym = String(r.symbol)
              const bucket = String(r.bucket ?? 'hold')
              const isOpen = open.has(sym)
              return [
                <tr
                  key={sym}
                  onClick={() => toggleRow(sym)}
                  className="cursor-pointer border-b border-hairline/50 transition-colors hover:bg-elevated/50"
                >
                  <td className={`${cellCls} font-sans`}>
                    <Link
                      href={`/stock?sym=${encodeURIComponent(sym)}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-mono text-xs font-semibold text-ink hover:text-accent"
                    >
                      {sym}
                    </Link>
                    {r.kind === 'watch' && (
                      <span className="ml-1.5 rounded-full border border-hairline px-1.5 py-0.5 text-[9px] text-faint">
                        watch
                      </span>
                    )}
                    {r.spec && (
                      <span className="ml-1 rounded-full bg-accent/10 px-1.5 py-0.5 text-[9px] font-medium text-accent">
                        spec
                      </span>
                    )}
                  </td>
                  {visible.map((c) => (
                    <td key={c.key} className={`${cellCls} text-right`}>
                      {c.cell(r, { bookValue })}
                    </td>
                  ))}
                  <td className={`${cellCls} text-right font-sans`}>
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium ${BUCKET_TONE[bucket]}`}
                      title={r.action_label
                        ? `rule: ${r.action_label}${r.action_confidence ? ` · ${r.action_confidence}` : ''}`
                        : undefined}
                    >
                      {BUCKET_GLYPH[bucket] ?? ''}{' '}
                      {BUCKET_LABEL[bucket] ?? bucket}
                    </span>
                  </td>
                  <td className={`${cellCls} text-faint`}>
                    {isOpen ? '▾' : '▸'}
                  </td>
                </tr>,
                isOpen && (
                  <tr key={`${sym}-x`} className="border-b border-hairline/50 bg-elevated/30">
                    <td
                      colSpan={visible.length + 3}
                      className="px-3 py-2.5 text-xs text-muted"
                    >
                      <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px]">
                        {r.mom_state && (
                          <span>
                            tape {String(r.mom_state).replace(/_/g, ' ')}
                            {r.mom_prev && r.mom_prev !== r.mom_state &&
                              ` ← ${r.mom_prev}`}
                            {r.dip_phase && ` · ${String(r.dip_phase).replace(/_/g, ' ')}`}
                          </span>
                        )}
                        {r.stoch_w_zone && (
                          <span className={r.stoch_w_up ? 'text-aggressive' : 'text-defensive'}>
                            wk stoch {r.stoch_w_zone} {r.stoch_w_up ? '↑' : '↓'}
                          </span>
                        )}
                        {r.spring != null && r.spring >= 60 && (
                          <span className="text-accent">⚡spring {r.spring}</span>
                        )}
                        {r.sector_flow && (
                          <span>{r.sector_etf} {String(r.sector_flow)}</span>
                        )}
                        {r.gq_pct != null && <span>GQ {r.gq_pct}th</span>}
                        {r.earn_traj && r.earn_traj !== 'insufficient' && (
                          <span>earn traj {r.earn_traj}</span>
                        )}
                        {r.action_label && (
                          <span className="text-faint">
                            rule: {String(r.action_label)}
                          </span>
                        )}
                      </div>
                      {Array.isArray(r.why) && r.why.length > 0 && (
                        <div className="pt-1.5 leading-relaxed">
                          {r.why.map((w, i) => (
                            <div key={i}>· {w}</div>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                ),
              ]
            })}
          </tbody>
          {/* ---- totals ---- */}
          <tfoot>
            <tr className="border-t border-hairline bg-elevated/40">
              <td className={`${cellCls} font-sans font-medium text-ink`}>
                {bucketFilter
                  ? `${BUCKET_LABEL[bucketFilter]} total`
                  : 'Total'}
              </td>
              {visible.map((c) => (
                <td key={c.key} className={`${cellCls} text-right`}>
                  {c.key === 'cost' && money(totals.cost, 0)}
                  {c.key === 'value' && (
                    <span className="text-ink font-medium">
                      {money(totals.value, 0)}
                    </span>
                  )}
                  {c.key === 'pnld' && (
                    <span className={tone(totals.pnl)}>
                      {money(totals.pnl, 0)}
                    </span>
                  )}
                  {c.key === 'pnlp' && (
                    <span className={tone(totals.pnl)}>
                      {totals.cost
                        ? pct((totals.pnl / totals.cost) * 100) : '—'}
                    </span>
                  )}
                  {c.key === 'dayd' && (
                    <span className={tone(totals.day)}>
                      {money(totals.day, 0)}
                    </span>
                  )}
                </td>
              ))}
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
      {sorted.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">
          No positions match this filter.
        </p>
      )}
    </div>
  )
}
