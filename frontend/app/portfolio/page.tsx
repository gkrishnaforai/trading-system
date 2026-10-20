import Link from 'next/link'
import { api, type PulseRow } from '@/lib/api'
import { Section, Stat } from '@/components/regime'
import { WatchlistCard } from '@/components/watchlist'
import { TIER_LIMITS, currentTier } from '@/lib/tier'
import { listPortfolios, listHoldings } from '@/lib/portfolio'
import {
  AddHoldingForm, BookPicker,
  HoldingRow as UserHoldingRow, NewPortfolioForm,
} from '@/components/portfolio-crud'

const BUCKET_ORDER = [
  'reduce', 'trim', 'avoid', 'attention', 'add', 'stalk', 'hold',
]
const BUCKET_LABEL: Record<string, string> = {
  reduce: 'Reduce', trim: 'Trim', avoid: 'Avoid',
  attention: 'Attention', add: 'Add', stalk: 'Stalk', hold: 'Hold',
}
const BUCKET_TONE: Record<string, string> = {
  reduce: 'text-defensive', trim: 'text-caution', avoid: 'text-defensive',
  attention: 'text-caution', add: 'text-aggressive',
  stalk: 'text-constructive', hold: 'text-muted',
}

const FLOW_TONE: Record<string, string> = {
  inflow: 'text-aggressive', 'rotating in': 'text-constructive',
  outflow: 'text-defensive', 'rotating out': 'text-caution',
}

function money(v?: number | null, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return `$${Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })}`
}

function pct(v?: number | null, sign = true) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  const n = Number(v)
  return `${sign && n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function tone(v?: number | null) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 0 ? 'text-aggressive' : 'text-defensive'
}

function SectorBar({ rows }: { rows: PulseRow[] }) {
  const pos = rows.filter(
    (r) => r.kind === 'position' && r.shares && r.price,
  )
  const total = pos.reduce((a, r) => a + (r.shares ?? 0) * (r.price ?? 0), 0)
  if (!total) return null
  const bySector = new Map<string, number>()
  for (const r of pos) {
    const s = String(r.sector ?? 'other')
    bySector.set(s, (bySector.get(s) ?? 0) + (r.shares ?? 0) * (r.price ?? 0))
  }
  const segs = [...bySector.entries()].sort((a, b) => b[1] - a[1])
  const hues = ['#EA580C', '#15803D', '#0F766E', '#A16207', '#78716C',
    '#B91C1C', '#6E6960', '#46413A']
  return (
    <div className="pt-4">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-elevated">
        {segs.map(([s, v], i) => (
          <div
            key={s}
            style={{
              width: `${(v / total) * 100}%`,
              background: hues[i % hues.length]
            }}
            title={`${s} ${((v / total) * 100).toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="pt-2 flex flex-wrap gap-x-4 gap-y-1">
        {segs.slice(0, 6).map(([s, v], i) => (
          <span key={s} className="text-[11px] text-muted">
            <span
              className="inline-block h-2 w-2 rounded-full mr-1"
              style={{ background: hues[i % hues.length] }}
            />
            {s} <span className="font-mono">
              {((v / total) * 100).toFixed(0)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

function HoldingRow({ r, bookValue }: { r: PulseRow; bookValue: number }) {
  const value = (r.shares ?? 0) * (r.price ?? 0)
  const weight = bookValue > 0 ? (value / bookValue) * 100 : null
  const bucket = String(r.bucket ?? 'hold')
  return (
    <div className="py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href={`/stock?sym=${encodeURIComponent(String(r.symbol ?? ''))}`}
            className="font-semibold text-ink hover:text-accent"
          >
            {r.symbol}
          </Link>
          {r.kind === 'watch' && (
            <span className="rounded-full border border-hairline px-2 py-0.5 text-[10px] text-muted">
              watch
            </span>
          )}
          {r.spec && (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
              spec
            </span>
          )}
          <span className={`text-xs font-medium ${BUCKET_TONE[bucket]}`}>
            {BUCKET_LABEL[bucket] ?? bucket}
          </span>
        </div>
        <div className="flex items-baseline gap-4 shrink-0 font-mono text-xs">
          {weight != null && (
            <span className="text-faint w-12 text-right">
              {weight.toFixed(1)}%
            </span>
          )}
          <span className="text-muted">{money(r.price, 2)}</span>
          <span className={`w-16 text-right ${tone(r.pnl_pct)}`}>
            {pct(r.pnl_pct)}
          </span>
          {r.fv_upside != null && (
            <span
              className={`w-14 text-right ${tone(r.fv_upside)}`}
              title="FV upside"
            >
              FV {pct(r.fv_upside)}
            </span>
          )}
        </div>
      </div>
      <div className="pt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted">
        {r.shares != null && r.kind === 'position' && (
          <span>{r.shares.toLocaleString()} × {money(r.avg_cost, 2)}</span>
        )}
        {r.mom_state && (
          <span>
            mom {r.mom_state}
            {r.dip_phase &&
              ['knife', 'capitulation', 'downtrend', 'breakdown', 'pullback']
                .includes(String(r.mom_state)) &&
              ` · ${String(r.dip_phase).replace(/_/g, ' ')}`}
            {r.spring != null && r.spring >= 60 && (
              <span className="text-accent" title="elastic — deep wash +
intact thesis + high vol: rips when the tape turns">
                {' '}⚡spring {r.spring}
              </span>
            )}
            {r.mom_prev && r.mom_prev !== r.mom_state &&
              ` ← ${r.mom_prev}`}
          </span>
        )}
        {r.fund_state && <span>fund {r.fund_state}</span>}
        {r.sector_flow && (
          <span className={FLOW_TONE[String(r.sector_flow)] ?? ''}>
            {r.sector_etf} {String(r.sector_flow)}
          </span>
        )}
        {r.revision_grade && <span>rev {r.revision_grade}</span>}
        {r.gq_pct != null && <span>GQ {r.gq_pct}th</span>}
      </div>
      {Array.isArray(r.why) && r.why.length > 0 && (
        <div className="pt-1 text-xs text-muted leading-relaxed">
          · {r.why.slice(0, 2).join(' · ')}
        </div>
      )}
    </div>
  )
}

export default async function PortfolioPage({
  searchParams,
}: {
  searchParams: { p?: string }
}) {
  const [pulse, portfolios] = await Promise.all([
    api.portfolioPulse(),
    listPortfolios(),
  ])
  const rows = pulse?.rows ?? []
  const book = pulse?.book
  const tier = currentTier()
  const limit = TIER_LIMITS[tier].portfolios

  const sel = searchParams.p ?? 'book'
  const selected = portfolios.find((p) => p.id === sel)
  const holdings = selected ? await listHoldings(selected.id) : null

  const groups = BUCKET_ORDER
    .map((b) => [b, rows.filter((r) => r.bucket === b)] as const)
    .filter(([, rs]) => rs.length > 0)

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-6">
        <div className="flex items-baseline justify-between">
          <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Portfolio
          </span>
          <span className="font-mono text-[11px] text-faint">
            {portfolios.length} of {limit} books · {pulse?.as_of}
          </span>
        </div>

        {/* book selector */}
        <div className="pt-3 flex items-center gap-2">
          <BookPicker
            options={portfolios}
            selected={selected?.id ?? 'book'}
          />
          <NewPortfolioForm used={portfolios.length} limit={limit} />
        </div>
      </header>

      {selected ? (
        /* ---- a user book: its holdings + CRUD ---- */
        <>
          <div className="flex items-baseline justify-between pb-4">
            <h1 className="font-semibold text-display text-ink">
              {selected.name}
            </h1>
            <span className="font-mono text-xs text-muted">
              {selected.initial_capital != null &&
                `$${Number(selected.initial_capital).toLocaleString()}`}
              {selected.portfolio_type &&
                ` · ${selected.portfolio_type}`}
            </span>
          </div>
          <section className="rounded-xl border border-hairline bg-card px-5 py-4">
            <AddHoldingForm portfolioId={selected.id} />
            <div className="mt-3 divide-y divide-hairline/60">
              {(holdings ?? []).length === 0 ? (
                <p className="py-4 text-sm text-muted">
                  Empty book — add a symbol above (the pulse checks it
                  against tape + fundamentals on next read).
                </p>
              ) : (
                (holdings ?? []).map((h) => (
                  <UserHoldingRow key={h.symbol} p={selected.id} h={h} />
                ))
              )}
            </div>
          </section>
          <div className="mt-6">
            <WatchlistCard />
          </div>
          <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
            advisory — your book, your call. Rename/delete for books
            lands with account sign-in.
          </footer>
        </>
      ) : (
        /* ---- the system book: pulse view ---- */
        <>
          <div className="pt-3 flex items-baseline gap-4">
            <h1 className="font-semibold text-display text-ink">
              {money(book?.value)}
            </h1>
            <span className={`font-mono text-xl ${tone(book?.pnl_pct)}`}>
              {pct(book?.pnl_pct)}
            </span>
          </div>
          {book?.on_pace != null && (
            <div className="pt-2 flex flex-wrap items-center gap-2 text-xs">
              <span
                className={`rounded-full px-2.5 py-1 font-medium ${book.on_pace
                  ? 'bg-aggressive/10 text-aggressive'
                  : 'bg-accent/10 text-accent'
                  }`}
              >
                {book.on_pace ? 'on pace' : 'behind pace'} vs{' '}
                {book.target_pct}% target
              </span>
              {book.track_ret_pct != null && (
                <span className="text-muted">
                  {pct(book.track_ret_pct)} over {book.track_days}d
                  {book.excess_pct != null && (
                    <span className={tone(book.excess_pct)}>
                      {' '}({pct(book.excess_pct)} vs SPY)
                    </span>
                  )}
                </span>
              )}
            </div>
          )}
          <SectorBar rows={rows} />

          <section className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-6 rounded-xl border border-hairline bg-card px-5 py-4">
            <Stat label="Positions" value={String(book?.positions ?? 0)} />
            <Stat label="Cost" value={money(book?.cost)} />
            <Stat label="Unrealized" value={money(book?.pnl)} />
            <Stat label="Goal /mo" value={money(book?.goal_month)} />
          </section>

          <Section title="Holdings" subtitle="attention first" defaultOpen>
            {rows.length === 0 ? (
              <p className="text-sm text-muted">
                No positions on the book. When holdings are journaled they
                appear here with tape state, FV gap and action hints.
              </p>
            ) : (
              groups.map(([bucket, rs]) => (
                <div key={bucket} className="mb-5 last:mb-0">
                  <div
                    className={`pb-1.5 text-[11px] font-semibold uppercase tracking-wider ${BUCKET_TONE[bucket]}`}
                  >
                    {BUCKET_LABEL[bucket] ?? bucket} · {rs.length}
                  </div>
                  <div className="divide-y divide-hairline/60">
                    {rs.map((r) => (
                      <HoldingRow key={r.symbol} r={r}
                        bookValue={book?.value ?? 0} />
                    ))}
                  </div>
                </div>
              ))
            )}
          </Section>

          <div className="mt-6">
            <WatchlistCard />
          </div>

          <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
            advisory — the action hints are deterministic evals; the trade is
            yours. Per-user books (1 member · 5 pro · 20 elite) turn on with
            sign-in.
          </footer>
        </>
      )}
    </main>
  )
}
