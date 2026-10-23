import Link from 'next/link'
import { api, type PulseRow } from '@/lib/api'
import { WatchlistCard } from '@/components/watchlist'
import { TIER_LIMITS, currentTier } from '@/lib/tier'
import { listPortfolios, listHoldings } from '@/lib/portfolio'
import {
  AddHoldingForm, AddPositionDock, BookRail,
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
const BUCKET_DOT: Record<string, string> = {
  reduce: '#B91C1C', trim: '#A16207', avoid: '#B91C1C',
  attention: '#A16207', add: '#15803D',
  stalk: '#0F766E', hold: '#57534C',
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

/** Dark command-deck hero — the cockpit readout. */
function Deck({
  kicker, right, children,
}: {
  kicker: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-[#0D0C0A] text-white">
      {/* glow + grid texture */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 80% at 15% 0%, rgba(234,88,12,0.22), transparent 60%),' +
            'radial-gradient(ellipse 50% 70% at 90% 110%, rgba(15,118,110,0.15), transparent 60%),' +
            'repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 28px),' +
            'repeating-linear-gradient(90deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 28px)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            'linear-gradient(90deg, transparent, rgba(234,88,12,0.7), transparent)',
        }}
      />
      <div className="relative px-6 py-5">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[11px] uppercase tracking-[0.25em] text-white/50">
            {kicker}
          </span>
          <span className="font-mono text-[11px] text-white/40">{right}</span>
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
    <div className="rounded-lg border border-white/[0.07] bg-white/[0.03] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-sm ${toneCls ?? 'text-white/90'}`}>
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
      <div className="flex h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
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
          <span key={s} className="text-[11px] text-white/55">
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

function HoldingRow({ r, bookValue }: { r: PulseRow; bookValue: number }) {
  const value = (r.shares ?? 0) * (r.price ?? 0)
  const weight = bookValue > 0 ? (value / bookValue) * 100 : null
  const bucket = String(r.bucket ?? 'hold')
  return (
    <div className="group rounded-lg px-2.5 py-3 transition-colors hover:bg-elevated/70">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href={`/stock?sym=${encodeURIComponent(String(r.symbol ?? ''))}`}
            className="font-mono text-sm font-semibold text-ink hover:text-accent"
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
      {/* weight rail */}
      {weight != null && (
        <div className="pt-1.5">
          <div className="h-0.5 rounded-full bg-elevated">
            <div
              className="h-0.5 rounded-full bg-accent/70"
              style={{ width: `${Math.min(weight, 100)}%` }}
            />
          </div>
        </div>
      )}
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
            {r.stoch_w_up != null && (
              <span
                className={
                  r.stoch_w_up ? 'text-aggressive' : 'text-defensive'
                }
                title={`weekly stochastic ${r.stoch_w_up ? 'rising' : 'falling'}` +
                  (r.stoch_w_zone ? ` · ${r.stoch_w_zone}` : '') +
                  (r.stoch_d_cross ? ` · daily ${r.stoch_d_cross} cross` : '')}
              >
                {' '}wk{r.stoch_w_zone === 'oversold' ? ' os' : ''}
                {r.stoch_w_up ? '↑' : '↓'}
                {r.stoch_d_cross === 'bull' ? '⇈' : ''}
              </span>
            )}
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

  const rail = (
    <div className="flex items-stretch gap-2">
      <div className="min-w-0 flex-1">
        <BookRail options={portfolios} selected={selected?.id ?? null} />
      </div>
      <NewPortfolioForm used={portfolios.length} limit={limit} />
    </div>
  )

  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      {selected ? (
        /* ---- a user book: its holdings + CRUD ---- */
        <>
          <div className="pt-6">
            <Deck
              kicker={`Portfolio · ${selected.portfolio_type ?? 'book'}`}
              right={`${pulse?.as_of ?? ''} · ${portfolios.length}/${limit} books`}
            >
              <div className="pt-4 flex items-baseline gap-4">
                <h1 className="font-semibold text-[clamp(1.4rem,3vw,2rem)] tracking-tight text-white">
                  {selected.name}
                </h1>
                <span className="font-mono text-sm text-white/50">
                  {selected.holdings_count ?? holdings?.length ?? 0} positions
                </span>
              </div>
              <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
                <DeckStat
                  label="Initial capital"
                  value={money(selected.initial_capital)}
                />
                <DeckStat
                  label="Invested"
                  value={money(selected.total_invested)}
                />
                <DeckStat label="Currency"
                  value={selected.currency ?? 'USD'} />
                <DeckStat
                  label="Since"
                  value={selected.created_at
                    ? new Date(selected.created_at)
                      .toLocaleDateString('en-US',
                        { month: 'short', day: 'numeric', year: '2-digit' })
                    : '—'}
                />
              </div>
            </Deck>
          </div>

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
                    {holdings?.length ?? 0} held
                  </span>
                </div>
                <div className="mt-2 divide-y divide-hairline/60">
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
            </div>
            <div className="space-y-4">
              <WatchlistCard />
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
          <div className="pt-6">
            <Deck
              kicker="Portfolio · the book"
              right={`${pulse?.as_of ?? ''} · ${portfolios.length}/${limit} books`}
            >
              <div className="pt-4 flex flex-wrap items-baseline gap-x-5 gap-y-2">
                <h1 className="font-mono text-[clamp(1.9rem,4.5vw,2.9rem)] font-semibold tracking-tight text-white">
                  {money(book?.value)}
                </h1>
                <span
                  className={`font-mono text-xl ${Number(book?.pnl_pct) >= 0
                    ? 'text-emerald-400'
                    : 'text-red-400'
                    }`}
                >
                  {pct(book?.pnl_pct)}
                </span>
                {book?.on_pace != null && (
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${book.on_pace
                      ? 'bg-emerald-400/15 text-emerald-300'
                      : 'bg-accent/20 text-orange-300'
                      }`}
                  >
                    {book.on_pace ? 'on pace' : 'behind pace'} vs{' '}
                    {book.target_pct}% target
                  </span>
                )}
                {book?.track_ret_pct != null && (
                  <span className="text-xs text-white/50">
                    {pct(book.track_ret_pct)} over {book.track_days}d
                    {book.excess_pct != null && (
                      <span
                        className={
                          Number(book.excess_pct) >= 0
                            ? 'text-emerald-400'
                            : 'text-red-400'
                        }
                      >
                        {' '}({pct(book.excess_pct)} vs SPY)
                      </span>
                    )}
                  </span>
                )}
              </div>
              <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
                <DeckStat label="Positions"
                  value={String(book?.positions ?? 0)} />
                <DeckStat label="Cost" value={money(book?.cost)} />
                <DeckStat
                  label="Unrealized"
                  value={money(book?.pnl)}
                  toneCls={
                    Number(book?.pnl) >= 0
                      ? 'text-emerald-400'
                      : 'text-red-400'
                  }
                />
                <DeckStat label="Goal /mo" value={money(book?.goal_month)} />
              </div>
              <SectorBar rows={rows} />
            </Deck>
          </div>

          <div className="pt-4">{rail}</div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <section className="lg:col-span-2 rounded-xl border border-hairline bg-card px-5 py-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
                  Holdings
                </span>
                <span className="font-mono text-[11px] text-faint">
                  attention first · {rows.length} names
                </span>
              </div>
              {rows.length === 0 ? (
                <p className="pt-4 text-sm text-muted">
                  No positions on the book. When holdings are journaled they
                  appear here with tape state, FV gap and action hints.
                </p>
              ) : (
                groups.map(([bucket, rs]) => (
                  <div key={bucket} className="mt-5 first:mt-3">
                    <div className="flex items-center gap-2 pb-2">
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: BUCKET_DOT[bucket] }}
                      />
                      <span
                        className={`text-[11px] font-semibold uppercase tracking-wider ${BUCKET_TONE[bucket]}`}
                      >
                        {BUCKET_LABEL[bucket] ?? bucket}
                      </span>
                      <span className="font-mono text-[11px] text-faint">
                        {rs.length}
                      </span>
                      <span className="h-px flex-1 bg-hairline/60" />
                    </div>
                    <div className="divide-y divide-hairline/50">
                      {rs.map((r) => (
                        <HoldingRow key={r.symbol} r={r}
                          bookValue={book?.value ?? 0} />
                      ))}
                    </div>
                  </div>
                ))
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
