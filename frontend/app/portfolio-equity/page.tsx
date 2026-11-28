import { api, type HealthRow } from '@/lib/api'
import { WatchlistCard } from '@/components/watchlist'
import { TIER_LIMITS, currentTier } from '@/lib/tier'
import { listPortfolios, listHoldings } from '@/lib/portfolio'
import { getUser } from '@/lib/auth'
import {
  AddHoldingForm, AddPositionDock, BookSelect, DeleteBookButton,
  HoldingRow as UserHoldingRow, NewPortfolioForm,
} from '@/components/portfolio-crud'
import { HealthTable } from '@/components/health-table'
import { BookAlerts } from '@/components/book-alerts'
import { Deck, DeckStat, scoreHealthTone } from '@/components/deck'

/** Portfolio · Equity Health — the portfolio cockpit's SEC-data twin.
    Same shell and book machinery; the readout is company health from
    EDGAR filings only — no price, no market data. */

function num(v?: number | null, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })
}

/** The cockpit readout, health edition: avg score + trend mix instead
    of value / today / unrealized. */
function HealthHero({ kicker, title, sub, right, rows, total }: {
  kicker: string
  title: string
  sub?: React.ReactNode
  right?: string
  rows: HealthRow[]
  total: number
}) {
  const scored = rows.filter((r) => r.verdict === 'scored' &&
    r.score != null)
  const avg = scored.length
    ? scored.reduce((a, r) => a + Number(r.score), 0) / scored.length
    : null
  const improving = rows.filter((r) => r.trend === 'improving').length
  const deteriorating =
    rows.filter((r) => r.trend === 'deteriorating').length
  const insufficient =
    rows.filter((r) => r.verdict === 'insufficient_data').length
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
          <span
            className={`font-mono text-[clamp(1.7rem,4vw,2.6rem)] font-semibold tracking-tight ${avg != null ? scoreHealthTone(avg) : 'text-ink'}`}
            title="equal-weight mean of scored positions"
          >
            {avg != null ? avg.toFixed(0) : '—'}
          </span>
          <span className="font-mono text-sm text-muted">
            avg health
          </span>
          {improving + deteriorating > 0 && (
            <span className="text-xs text-muted">
              <span className="text-aggressive font-medium">
                {improving} improving
              </span>
              {' · '}
              <span className="text-defensive font-medium">
                {deteriorating} deteriorating
              </span>
            </span>
          )}
        </div>
        <div className="pt-4 grid grid-cols-2 sm:grid-cols-5 gap-2">
          <DeckStat label="Positions" value={String(total)} />
          <DeckStat label="Scored" value={String(scored.length)} />
          <DeckStat
            label="Avg health"
            value={avg != null ? avg.toFixed(0) : '—'}
            toneCls={avg != null ? scoreHealthTone(avg) : undefined}
          />
          <DeckStat label="Improving" value={String(improving)}
            toneCls="text-aggressive" />
          <DeckStat label="Below gate" value={String(insufficient)}
            toneCls={insufficient ? 'text-caution' : 'text-muted'} />
        </div>
      </Deck>
    </div>
  )
}

export default async function PortfolioEquityPage({
  searchParams,
}: {
  searchParams: { p?: string }
}) {
  const user = await getUser().catch(() => null)
  const portfolios = await listPortfolios()
  const tier = currentTier()
  const limit = TIER_LIMITS[tier].portfolios

  const sel = searchParams.p ?? 'book'
  const selected = portfolios.find((p) => p.id === sel)
  const alerts = user?.role === 'admin'
    ? await api.alerts({ hours: 36 }).catch(() => null)
    : null

  // holdings → the equity universe; health rows resolve per symbol.
  // Aggregate 'book' = union of every listed book's holdings.
  const books = selected ? [selected] : portfolios
  const holdingsPerBook = await Promise.all(
    books.map((b) => listHoldings(b.id).catch(() => [])),
  )
  const selectedHoldings = selected ? holdingsPerBook[0] : null
  const shares: Record<string, number | undefined> = {}
  const symbols = new Set<string>()
  for (const hs of holdingsPerBook) {
    for (const h of hs) {
      const sym = String(h.symbol ?? '').toUpperCase()
      if (!sym) continue
      symbols.add(sym)
      shares[sym] = (shares[sym] ?? 0) + Number(h.shares_held ?? 0)
    }
  }

  const board = symbols.size
    ? await api.companyHealth([...symbols]).catch(() => null)
    : null
  const bySym = new Map(
    (board?.items ?? []).map((r) => [String(r.symbol).toUpperCase(), r]),
  )
  // every book symbol gets a row — unscored names surface as n/a, not
  // silently missing (a missing leg must never read as a clean score)
  const rows: HealthRow[] = [...symbols].sort().map(
    (s) => bySym.get(s) ?? {
      symbol: s, verdict: 'insufficient_data', trend: null,
      score: null, coverage_pct: null,
    },
  )

  const rail = (
    <div className="flex items-stretch gap-2">
      <BookSelect options={portfolios} selected={selected?.id ?? null}
        base="/portfolio-equity" />
      <NewPortfolioForm used={portfolios.length} limit={limit} />
    </div>
  )

  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <BookAlerts items={alerts?.items ?? []} symbols={symbols} />
      <HealthHero
        kicker={selected
          ? `Equity health · ${selected.portfolio_type ?? 'book'}`
          : 'Equity health · the book'}
        title={selected ? selected.name : 'The book — fundamentals'}
        sub={
          <span className="font-mono text-xs text-muted">
            {symbols.size} positions · SEC EDGAR filings only
            {selected?.currency && ` · ${selected.currency}`}
          </span>
        }
        right={`scored ${board?.as_of?.slice(0, 10) ?? '—'}`}
        rows={rows}
        total={symbols.size}
      />

      <div className="pt-4">{rail}</div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          {selected && <AddHoldingForm portfolioId={selected.id} />}
          <section className="rounded-xl border border-hairline bg-card px-5 py-4">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                Holdings — fundamentals
              </span>
              <span className="font-mono text-[11px] text-faint">
                click a row for the quarterly detail · {rows.length} names
              </span>
            </div>
            {rows.length === 0 ? (
              <p className="pt-4 text-sm text-muted">
                No positions on the book. Add a symbol above — its
                SEC-filing health shows up here once the EDGAR jobs
                resolve and score it.
              </p>
            ) : (
              <div className="pt-3">
                <HealthTable rows={rows} shares={shares} />
              </div>
            )}
          </section>
        </div>
        <div className="space-y-4">
          {!selected && <AddPositionDock books={portfolios} />}
          <WatchlistCard />
          {selected && (
            <section className="rounded-xl border border-hairline bg-card px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                  Manage
                </span>
                <span className="font-mono text-[11px] text-faint">
                  {selectedHoldings?.length ?? 0} held
                </span>
              </div>
              <div className="mt-2 divide-y divide-hairline/60">
                {(selectedHoldings ?? []).map((h) => (
                  <UserHoldingRow key={h.symbol} p={selected.id} h={h} />
                ))}
              </div>
              <div className="mt-3 flex justify-end border-t border-hairline/60 pt-3">
                <DeleteBookButton id={selected.id} name={selected.name} />
              </div>
            </section>
          )}
          <div className="rounded-xl border border-hairline bg-elevated/50 px-5 py-4 text-[11px] leading-relaxed text-faint">
            Company health is computed only from SEC EDGAR filings
            (10-Q / 10-K / amendments) — coverage-gated quarterly
            scores, earnings-quality legs and filing-linked red flags.
            Not an investment recommendation.
          </div>
        </div>
      </div>
    </main>
  )
}
