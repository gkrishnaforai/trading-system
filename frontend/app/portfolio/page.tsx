import Link from 'next/link'
import { api, type PulseBook, type PulseRow } from '@/lib/api'
import { WatchlistCard } from '@/components/watchlist'
import { TIER_LIMITS, currentTier } from '@/lib/tier'
import { listPortfolios, listHoldings } from '@/lib/portfolio'
import { getUser } from '@/lib/auth'
import {
  AddHoldingForm, AddPositionDock, BookSelect, DeleteBookButton,
  HoldingRow as UserHoldingRow, NewPortfolioForm,
} from '@/components/portfolio-crud'
import { PortfolioTable } from '@/components/portfolio-table'
import { BookAlerts } from '@/components/book-alerts'

function money(v?: number | null, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return `$${Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })}`
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

/** Light command-deck hero — the cockpit readout. Soft-paper gradient,
    hairline grid, accent glow edge. */
function Deck({
  kicker, right, children,
}: {
  kicker: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-hairline bg-[#FAF9F7] text-ink shadow-[0_1px_2px_rgba(13,12,10,0.04),0_12px_32px_-16px_rgba(13,12,10,0.12)]">
      {/* glow + grid texture */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 80% at 15% 0%, rgba(234,88,12,0.08), transparent 60%),' +
            'radial-gradient(ellipse 50% 70% at 90% 110%, rgba(15,118,110,0.07), transparent 60%),' +
            'repeating-linear-gradient(0deg, rgba(13,12,10,0.028) 0 1px, transparent 1px 28px),' +
            'repeating-linear-gradient(90deg, rgba(13,12,10,0.028) 0 1px, transparent 1px 28px)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            'linear-gradient(90deg, transparent, rgba(234,88,12,0.55), transparent)',
        }}
      />
      <div className="relative px-6 py-5">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[11px] uppercase tracking-[0.25em] text-faint">
            {kicker}
          </span>
          <span className="font-mono text-[11px] text-faint">{right}</span>
        </div>
        {children}
      </div>
    </div>
  )
}

function DeckStat({ label, value, toneCls }: {
  label: string; value: string; toneCls?: string
}) {
  return (
    <div className="rounded-lg border border-hairline bg-white/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-faint">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-sm ${toneCls ?? 'text-ink'}`}>
        {value}
      </div>
    </div>
  )
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
  const hues = ['#EA580C', '#2DD4BF', '#F59E0B', '#38BDF8', '#A78BFA',
    '#F87171', '#A3E635', '#94A3B8']
  return (
    <div className="pt-4">
      <div className="flex h-1.5 overflow-hidden rounded-full bg-elevated">
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
              className="inline-block h-1.5 w-1.5 rounded-full mr-1.5"
              style={{ background: hues[i % hues.length] }}
            />
            {s}{' '}
            <span className="font-mono">
              {((v / total) * 100).toFixed(0)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

/** "What happened today" — top day movers + biggest $ swings. */
function TodayStrip({ rows }: { rows: PulseRow[] }) {
  const pos = rows.filter(
    (r) => r.kind === 'position' && r.day_chg_pct != null,
  )
  if (!pos.length) return null
  const byPct = [...pos].sort(
    (a, b) => Number(b.day_chg_pct) - Number(a.day_chg_pct),
  )
  const day$ = (r: PulseRow) =>
    (r.shares ?? 0) * (Number(r.price) - Number(r.prev_close))
  const by$ = [...pos].sort((a, b) => Math.abs(day$(b)) - Math.abs(day$(a)))
  const winners = byPct.slice(0, 3)
  const losers = byPct.slice(-3).reverse()
    .filter((r) => Number(r.day_chg_pct) < 0)
  const mover = by$[0]
  const Item = ({ r, sub }: { r: PulseRow; sub: string }) => (
    <Link
      href={`/stock?sym=${encodeURIComponent(String(r.symbol))}`}
      className="flex items-baseline justify-between gap-3 rounded-lg border border-hairline bg-white/70 px-3 py-2 hover:border-accent/40 transition-colors"
    >
      <span className="font-mono text-xs font-semibold text-ink">
        {r.symbol}
      </span>
      <span className="font-mono text-[11px]">
        <span className={tone(r.day_chg_pct)}>
          {pct(r.day_chg_pct, true, 2)}
        </span>
        <span className="text-faint"> · {sub}</span>
      </span>
    </Link>
  )
  return (
    <div className="pt-5">
      <div className="flex items-baseline justify-between pb-2">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Today
        </span>
        {mover && (
          <span className="font-mono text-[11px] text-faint">
            biggest swing {mover.symbol}{' '}
            <span className={tone(day$(mover))}>
              {money(day$(mover), 0)}
            </span>
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {winners.map((r) => (
          <Item key={`w-${r.symbol}`} r={r}
            sub={money(day$(r), 0)} />
        ))}
        {losers.map((r) => (
          <Item key={`l-${r.symbol}`} r={r}
            sub={money(day$(r), 0)} />
        ))}
      </div>
    </div>
  )
}

/** The command-deck readout shared by the aggregate book and any
    single user book — value, today, unrealized, pace, stats,
    day movers and sector mix. */
function BookHero({ kicker, title, sub, right, book, rows }: {
  kicker: string
  title: string
  sub?: React.ReactNode
  right?: string
  book?: PulseBook
  rows: PulseRow[]
}) {
  return (
    <div className="pt-6">
      <Deck kicker={kicker} right={right}>
        <div className="pt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="font-semibold text-[clamp(1.3rem,2.8vw,1.8rem)] tracking-tight text-ink">
            {title}
          </h1>
          {sub}
        </div>
        <div className="pt-2 flex flex-wrap items-baseline gap-x-5 gap-y-2">
          <span className="font-mono text-[clamp(1.7rem,4vw,2.6rem)] font-semibold tracking-tight text-ink">
            {money(book?.value)}
          </span>
          {book?.day_chg_pct != null && (
            <span
              className={`font-mono text-xl ${Number(book.day_chg_pct) >= 0
                ? 'text-aggressive'
                : 'text-defensive'
                }`}
              title="today vs previous close"
            >
              {pct(book.day_chg_pct, true, 2)}
              <span className="text-sm"> today</span>
            </span>
          )}
          <span
            className={`font-mono text-xl ${Number(book?.pnl_pct) >= 0
              ? 'text-aggressive'
              : 'text-defensive'
              }`}
            title="unrealized vs cost"
          >
            {pct(book?.pnl_pct)}
          </span>
          {book?.on_pace != null && (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${book.on_pace
                ? 'bg-aggressive/10 text-aggressive'
                : 'bg-accent/10 text-accent'
                }`}
            >
              {book.on_pace ? 'on pace' : 'behind pace'} vs{' '}
              {book.target_pct}% target
            </span>
          )}
          {book?.track_ret_pct != null && (book.track_days ?? 0) > 0 && (
            <span className="text-xs text-muted">
              {pct(book.track_ret_pct)} over {book.track_days}d
              {book.excess_pct != null && (
                <span
                  className={
                    Number(book.excess_pct) >= 0
                      ? 'text-aggressive'
                      : 'text-defensive'
                  }
                >
                  {' '}({pct(book.excess_pct)} vs SPY)
                </span>
              )}
            </span>
          )}
        </div>
        <div className="pt-4 grid grid-cols-2 sm:grid-cols-5 gap-2">
          <DeckStat label="Positions"
            value={String(book?.positions ?? 0)} />
          <DeckStat label="Cost" value={money(book?.cost)} />
          <DeckStat
            label="Unrealized"
            value={money(book?.pnl)}
            toneCls={
              Number(book?.pnl) >= 0
                ? 'text-aggressive'
                : 'text-defensive'
            }
          />
          <DeckStat
            label="Day P/L"
            value={book?.day_pnl != null ? money(book.day_pnl) : '—'}
            toneCls={
              Number(book?.day_pnl) >= 0
                ? 'text-aggressive'
                : 'text-defensive'
            }
          />
          <DeckStat label="Goal /mo" value={money(book?.goal_month)} />
        </div>
        <TodayStrip rows={rows} />
        <SectorBar rows={rows} />
      </Deck>
    </div>
  )
}

export default async function PortfolioPage({
  searchParams,
}: {
  searchParams: { p?: string }
}) {
  const user = await getUser().catch(() => null)
  // non-admin sees only their own books — pass user_id so the
  // aggregate 'book' view unions THEIR holdings, not everyone's
  const uid = user?.role === 'admin' ? undefined : user?.id
  const [pulse, portfolios, alerts] = await Promise.all([
    api.portfolioPulse(undefined, uid),
    listPortfolios(),
    user?.role === 'admin'
      ? api.alerts({ hours: 36 }).catch(() => null)
      : Promise.resolve(null),
  ])
  const tier = currentTier()
  const limit = TIER_LIMITS[tier].portfolios

  const sel = searchParams.p ?? 'book'
  const selected = portfolios.find((p) => p.id === sel)
  const [scoped, holdings] = selected
    ? await Promise.all([
      api.portfolioPulse(selected.id, uid),
      listHoldings(selected.id),
    ])
    : [null, null]

  const view = selected ? scoped : pulse
  const rows = view?.rows ?? []
  const book = view?.book
  const bookSyms = new Set([
    ...rows.map((r) => String(r.symbol ?? '').toUpperCase()),
    ...(holdings ?? []).map((h) => String(h.symbol ?? '').toUpperCase()),
  ])

  const rail = (
    <div className="flex items-stretch gap-2">
      <BookSelect options={portfolios} selected={selected?.id ?? null} />
      <NewPortfolioForm used={portfolios.length} limit={limit} />
    </div>
  )

  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <BookAlerts items={alerts?.items ?? []}
        symbols={bookSyms} />
      {selected ? (
        /* ---- a user book: same cockpit, scoped to the book ---- */
        <>
          <BookHero
            kicker={`Portfolio · ${selected.portfolio_type ?? 'book'}`}
            title={selected.name}
            sub={
              <span className="font-mono text-xs text-muted">
                {book?.positions ?? holdings?.length ?? 0} positions
                {selected.currency && ` · ${selected.currency}`}
                {selected.created_at &&
                  ` · since ${new Date(selected.created_at)
                    .toLocaleDateString('en-US',
                      { month: 'short', year: '2-digit' })}`}
              </span>
            }
            right={`${view?.as_of ?? ''}`}
            book={book}
            rows={rows}
          />

          <div className="pt-4">{rail}</div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-4">
              <AddHoldingForm portfolioId={selected.id} />
              <section className="rounded-xl border border-hairline bg-card px-5 py-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                    Positions
                  </span>
                  <span className="font-mono text-[11px] text-faint">
                    click a row for the engine's reasoning ·{' '}
                    {rows.length} names
                  </span>
                </div>
                {rows.length === 0 ? (
                  <p className="py-4 text-sm text-muted">
                    Empty book — add a symbol above (the pulse checks it
                    against tape + fundamentals on next read).
                  </p>
                ) : (
                  <div className="pt-3">
                    <PortfolioTable rows={rows}
                      bookValue={book?.value ?? 0} />
                  </div>
                )}
              </section>
            </div>
            <div className="space-y-4">
              <WatchlistCard />
              <section className="rounded-xl border border-hairline bg-card px-5 py-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                    Manage
                  </span>
                  <span className="font-mono text-[11px] text-faint">
                    {holdings?.length ?? 0} held
                  </span>
                </div>
                <div className="mt-2 divide-y divide-hairline/60">
                  {(holdings ?? []).map((h) => (
                    <UserHoldingRow key={h.symbol} p={selected.id} h={h} />
                  ))}
                </div>
                <div className="mt-3 flex justify-end border-t border-hairline/60 pt-3">
                  <DeleteBookButton id={selected.id} name={selected.name} />
                </div>
              </section>
              <div className="rounded-xl border border-hairline bg-elevated/50 px-5 py-4 text-[11px] leading-relaxed text-faint">
                Advisory — your book, your call. Records are journals;
                no orders are placed. Rename/delete for books lands
                with account sign-in.
              </div>
            </div>
          </div>
        </>
      ) : (
        /* ---- the system book: pulse view ---- */
        <>
          <BookHero
            kicker="Portfolio · the book"
            title="The book"
            sub={
              <span className="font-mono text-xs text-muted">
                all positions across {portfolios.length} book
                {portfolios.length === 1 ? '' : 's'}
              </span>
            }
            right={`${view?.as_of ?? ''}`}
            book={book}
            rows={rows}
          />

          <div className="pt-4">{rail}</div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <section className="lg:col-span-2 rounded-xl border border-hairline bg-card px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                  Holdings
                </span>
                <span className="font-mono text-[11px] text-faint">
                  click a row for the engine's reasoning ·{' '}
                  {rows.length} names
                </span>
              </div>
              {rows.length === 0 ? (
                <p className="pt-4 text-sm text-muted">
                  No positions on the book. When holdings are journaled they
                  appear here with tape state, FV gap and action hints.
                </p>
              ) : (
                <div className="pt-3">
                  <PortfolioTable rows={rows}
                    bookValue={book?.value ?? 0} />
                </div>
              )}
            </section>
            <div className="space-y-4">
              <AddPositionDock books={portfolios} />
              <WatchlistCard />
              <div className="rounded-xl border border-hairline bg-elevated/50 px-5 py-4 text-[11px] leading-relaxed text-faint">
                Advisory — the action hints are deterministic evals;
                the trade is yours. This view is read-only: open a
                book above to add, edit or remove positions.
              </div>
            </div>
          </div>
        </>
      )}
    </main>
  )
}
