import Link from 'next/link'
import {
  api, type HealthRow, type StatementRow, type FilingRow,
  type CompanyHealthDetail,
} from '@/lib/api'
import { Deck, DeckStat, scoreHealthTone } from '@/components/deck'

/** Equity — the per-symbol fundamentals page. Company health from
    SEC EDGAR quarterly/annual filings only: coverage-gated scores,
    category legs, drivers, red flags and the resolved statements.
    No price data, no licensed providers. */

function num(v?: number | string | null, dec = 0) {
  const n = Number(v)
  if (v === null || v === undefined || !Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })
}

/** big statement figures read better in millions */
function mm(v?: number | string | null) {
  const n = Number(v)
  if (v === null || v === undefined || !Number.isFinite(n)) return '—'
  const m = n / 1e6
  const dec = Math.abs(m) >= 1000 ? 0 : 1
  return `$${m.toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })}M`
}

const TREND_TONE: Record<string, string> = {
  improving: 'text-aggressive border-aggressive/30 bg-aggressive/10',
  stable: 'text-constructive border-constructive/30 bg-constructive/10',
  deteriorating:
    'text-defensive border-defensive/30 bg-defensive/10',
  new: 'text-muted border-hairline bg-elevated/60',
}

function Section({ title, right, children }: {
  title: string; right?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          {title}
        </span>
        <span className="font-mono text-[11px] text-faint">{right}</span>
      </div>
      <div className="pt-3">{children}</div>
    </section>
  )
}

/** quarterly score spine — newest left, read as a strip not a chart */
function ScoreStrip({ rows }: { rows: HealthRow[] }) {
  const scored = rows.filter((r) => r.score != null)
  if (!scored.length) return null
  return (
    <div className="flex items-end gap-1.5 overflow-x-auto pb-1">
      {[...scored].reverse().map((r) => {
        const h = Math.max(6, Math.round((Number(r.score) / 100) * 44))
        return (
          <Link
            key={r.period_end}
            href={`#q-${r.period_end}`}
            title={`${r.period_end} · ${r.score} · ${r.trend ?? ''}`}
            className="group flex flex-col items-center gap-1"
          >
            <span className={`font-mono text-[9px] ${scoreHealthTone(r.score)}`}>
              {r.score}
            </span>
            <span
              className={`w-6 rounded-sm transition-colors ${
                Number(r.score) >= 65 ? 'bg-aggressive/60'
                : Number(r.score) >= 40 ? 'bg-caution/60'
                : 'bg-defensive/60'} group-hover:bg-accent`}
              style={{ height: h }}
            />
            <span className="font-mono text-[9px] text-faint">
              {String(r.period_end).slice(2, 7)}
            </span>
          </Link>
        )
      })}
    </div>
  )
}

function Categories({ row }: { row: HealthRow }) {
  const cs = row.category_scores
  if (!cs) return <p className="text-sm text-muted">No category detail.</p>
  return (
    <div className="space-y-3">
      {Object.entries(cs).map(([name, cat]) => (
        <div key={name}>
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-medium text-ink capitalize">
              {name.replace(/_/g, ' ')}
            </span>
            <span className={`font-mono text-xs ${scoreHealthTone(cat.score)}`}>
              {cat.score != null ? cat.score : '—'}
              <span className="text-faint"> · w{num(cat.weight, 2)}</span>
            </span>
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-elevated">
            <div
              className={`h-full ${
                Number(cat.score) >= 65 ? 'bg-aggressive/70'
                : Number(cat.score) >= 40 ? 'bg-caution/70'
                : cat.score != null ? 'bg-defensive/70' : 'bg-hairline'}`}
              style={{
                width: `${Math.min(100, Math.max(0, Number(cat.score) || 0))}%`,
              }}
            />
          </div>
          {(cat.legs ?? []).length > 0 && (
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
              {(cat.legs ?? []).map((l, i) => (
                <span key={i} className="font-mono text-[10px] text-faint">
                  {l.name}:{' '}
                  <span className={scoreHealthTone(l.score)}>
                    {l.score ?? '—'}
                  </span>
                  {l.value != null && (
                    <span className="text-faint">
                      {' '}({num(l.value, 2)})
                    </span>
                  )}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function QuarterJournal({ rows }: { rows: HealthRow[] }) {
  return (
    <div className="space-y-4">
      {rows.map((r) => (
        <div key={r.period_end} id={`q-${r.period_end}`}
          className="rounded-lg border border-hairline px-4 py-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-xs font-semibold text-ink">
              {r.period_end}
            </span>
            {r.verdict === 'insufficient_data' ? (
              <span className="rounded-full border border-hairline bg-elevated/60 px-2 py-0.5 text-[10px] text-faint">
                insufficient data
              </span>
            ) : (
              <span className={`font-mono text-sm font-semibold ${scoreHealthTone(r.score)}`}>
                {r.score}
              </span>
            )}
            {r.score_delta != null && (
              <span className={`font-mono text-xs ${
                r.score_delta > 0 ? 'text-aggressive'
                : r.score_delta < 0 ? 'text-defensive' : 'text-muted'}`}>
                {r.score_delta > 0 ? '+' : ''}{r.score_delta} vs prior
              </span>
            )}
            {r.trend && (
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${TREND_TONE[r.trend] ?? 'text-muted border-hairline'}`}>
                {r.trend}
              </span>
            )}
            <span className="font-mono text-[10px] text-faint">
              coverage {num(r.coverage_pct)}% · {r.confidence ?? '—'} confidence
              {r.ewf_state ? ` · EWF ${r.ewf_state}` : ''}
              {r.quality_score != null ? ` · eq ${r.quality_score}` : ''}
            </span>
          </div>
          {(r.drivers ?? []).length > 0 && (
            <div className="mt-2 space-y-0.5">
              {(r.drivers ?? []).slice(0, 6).map((d, i) => (
                <div key={i} className="flex items-baseline gap-2 text-[11px]">
                  <span className={
                    d.direction === 'up' ? 'text-aggressive'
                    : d.direction === 'down' ? 'text-defensive'
                    : 'text-muted'}>
                    {d.direction === 'up' ? '▲'
                      : d.direction === 'down' ? '▼' : '◆'}
                  </span>
                  <span className="text-muted">{d.metric}</span>
                  <span className="font-mono text-faint">
                    {d.contribution != null
                      ? `${Number(d.contribution) > 0 ? '+' : ''}${num(d.contribution, 1)}`
                      : ''}
                  </span>
                  {d.evidence_accn && (
                    <span className="font-mono text-[9px] text-faint"
                      title={`evidence: ${d.evidence_accn}`}>
                      §{String(d.evidence_accn).slice(0, 18)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {(r.red_flags ?? []).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(r.red_flags ?? []).map((f, i) => (
                <span key={i}
                  title={f.evidence_accn ? `filing ${f.evidence_accn}` : ''}
                  className="rounded-full border border-defensive/30 bg-defensive/10 px-2 py-0.5 text-[10px] text-defensive">
                  ⚑ {f.class ?? 'flag'}: {f.pattern ?? ''}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function StatementTable({ rows, cols }: {
  rows: StatementRow[]
  cols: { key: string; label: string; money?: boolean }[]
}) {
  if (!rows.length)
    return <p className="text-sm text-muted">No resolved rows yet.</p>
  const headCls =
    'px-2 py-1.5 text-right font-sans text-[10px] font-medium ' +
    'uppercase tracking-wider text-faint whitespace-nowrap'
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-hairline">
            <th className={`${headCls} text-left`}>Period</th>
            {cols.map((c) => (
              <th key={c.key} className={headCls}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.period}
              className="border-b border-hairline/50">
              <td className="px-2 py-1.5 font-mono text-xs text-ink">
                {r.period}
              </td>
              {cols.map((c) => (
                <td key={c.key}
                  className="px-2 py-1.5 text-right font-mono text-xs text-muted">
                  {c.money ? mm(r[c.key]) : num(r[c.key], 2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Filings({ rows }: { rows: FilingRow[] }) {
  if (!rows.length)
    return <p className="text-sm text-muted">No filings journaled.</p>
  return (
    <div className="divide-y divide-hairline/60">
      {rows.map((f) => (
        <div key={f.accession_number}
          className="flex items-baseline justify-between gap-3 py-1.5">
          <span className="font-mono text-xs">
            <span className="font-semibold text-ink">{f.form}</span>
            {f.is_amendment && (
              <span className="ml-1.5 text-[10px] text-caution">
                amendment
              </span>
            )}
          </span>
          <span className="font-mono text-[10px] text-faint">
            filed {f.filing_date}
            {f.report_period ? ` · period ${f.report_period}` : ''}
          </span>
          {f.document_url ? (
            <a href={f.document_url} target="_blank" rel="noreferrer"
              className="font-mono text-[10px] text-accent hover:underline">
              filing ↗
            </a>
          ) : (
            <span className="font-mono text-[10px] text-faint">
              {f.accession_number}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function Hero({ d }: { d: CompanyHealthDetail }) {
  const latest = d.health?.[0]
  const ent = d.entity
  return (
    <Deck
      kicker="Equity · SEC filings"
      right={latest?.computed_at
        ? `scored ${String(latest.computed_at).slice(0, 10)}` : ''}
    >
      <div className="pt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-semibold text-[clamp(1.3rem,2.8vw,1.8rem)] tracking-tight text-ink">
          {d.symbol}
        </h1>
        <span className="font-mono text-xs text-muted">
          {ent?.entity_name ?? ''}
          {ent?.sic_description ? ` · ${ent.sic_description}` : ''}
          {ent?.fy_end ? ` · FY ends ${ent.fy_end}` : ''}
        </span>
      </div>
      <div className="pt-2 flex flex-wrap items-baseline gap-x-5 gap-y-2">
        {latest?.verdict === 'insufficient_data' ? (
          <span className="rounded-full border border-hairline bg-elevated/60 px-3 py-1 font-mono text-sm text-faint">
            insufficient data — category scores only
          </span>
        ) : (
          <span
            className={`font-mono text-[clamp(1.7rem,4vw,2.6rem)] font-semibold tracking-tight ${scoreHealthTone(latest?.score)}`}
          >
            {latest?.score ?? '—'}
          </span>
        )}
        {latest?.score_delta != null && (
          <span className={`font-mono text-xl ${
            latest.score_delta > 0 ? 'text-aggressive'
            : latest.score_delta < 0 ? 'text-defensive' : 'text-muted'}`}>
            {latest.score_delta > 0 ? '+' : ''}{latest.score_delta}
            <span className="text-sm"> vs prior qtr</span>
          </span>
        )}
        {latest?.trend && (
          <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${TREND_TONE[latest.trend] ?? 'text-muted border-hairline'}`}>
            {latest.trend}
          </span>
        )}
        {latest?.ewf_state && (
          <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
            latest.ewf_state === 'GREEN'
              ? 'border-aggressive/30 bg-aggressive/10 text-aggressive'
              : latest.ewf_state === 'YELLOW'
              ? 'border-caution/30 bg-caution/10 text-caution'
              : 'border-defensive/30 bg-defensive/10 text-defensive'}`}>
            EWF {latest.ewf_state}
          </span>
        )}
      </div>
      <div className="pt-4 grid grid-cols-2 sm:grid-cols-5 gap-2">
        <DeckStat label="Coverage"
          value={latest?.coverage_pct != null
            ? `${num(latest.coverage_pct)}%` : '—'} />
        <DeckStat label="Confidence"
          value={latest?.confidence ?? '—'} />
        <DeckStat label="Earnings quality"
          value={latest?.quality_score != null
            ? String(latest.quality_score) : '—'}
          toneCls={scoreHealthTone(latest?.quality_score)} />
        <DeckStat label="Quarters scored"
          value={String(d.health?.length ?? 0)} />
        <DeckStat label="Filings tracked"
          value={String(d.filings?.length ?? 0)} />
      </div>
      {latest && <div className="pt-5"><ScoreStrip rows={d.health ?? []} /></div>}
    </Deck>
  )
}

export default async function EquityPage({
  searchParams,
}: {
  searchParams: { sym?: string }
}) {
  const sym = (searchParams.sym ?? '').toUpperCase().trim()
  const [detail, board] = await Promise.all([
    sym ? api.companyHealthSymbol(sym, 12).catch(() => null) : null,
    api.companyHealth().catch(() => null),
  ])

  const quick = (board?.items ?? [])
    .filter((r) => r.verdict === 'scored')
    .sort((a, b) => Number(b.score) - Number(a.score))

  return (
    <main className="mx-auto max-w-5xl px-5 pb-20">
      <div className="pt-6">
        <form method="GET" className="flex items-center gap-2">
          <input
            name="sym" defaultValue={sym}
            placeholder="Ticker — NVDA"
            className="w-44 rounded-lg border border-hairline bg-card px-3 py-2 font-mono text-sm uppercase outline-none focus:border-accent/50"
          />
          <button className="rounded-lg border border-hairline px-3 py-2 text-xs font-medium text-muted hover:border-ink/20">
            Load
          </button>
          <div className="ml-2 flex flex-wrap gap-1.5">
            {quick.slice(0, 8).map((r) => (
              <Link key={r.symbol}
                href={`/equity?sym=${r.symbol}`}
                className={`rounded-full border px-2.5 py-1 text-[11px] font-mono transition-colors ${
                  sym === r.symbol
                    ? 'border-ink/30 bg-ink text-canvas'
                    : 'border-hairline text-muted hover:border-ink/20'}`}>
                {r.symbol} <span className={scoreHealthTone(r.score)}>
                  {r.score}
                </span>
              </Link>
            ))}
          </div>
        </form>
      </div>

      {!sym && (
        <div className="pt-10 text-center text-sm text-muted">
          Pick a ticker — the fundamentals dossier is built only from
          SEC EDGAR filings (10-Q / 10-K / amendments).
        </div>
      )}

      {sym && !detail?.health?.length && (
        <div className="pt-10 text-center text-sm text-muted">
          No resolved SEC data for <span className="font-mono">{sym}</span>
          {' '}yet — the EDGAR jobs score a symbol after its filings are
          scanned and facts resolved.
        </div>
      )}

      {detail?.health?.length ? (
        <>
          <div className="pt-6"><Hero d={detail} /></div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-4">
              <Section title="Quarterly journal"
                right="versioned — amendments rescore, never overwrite">
                <QuarterJournal rows={detail.health ?? []} />
              </Section>
              <Section title="Income statement"
                right="quarterly · sec_edgar">
                <StatementTable
                  rows={detail.statements?.income ?? []}
                  cols={[
                    { key: 'total_revenue', label: 'Rev', money: true },
                    { key: 'gross_profit', label: 'GP', money: true },
                    { key: 'operating_income', label: 'Op inc', money: true },
                    { key: 'net_income', label: 'Net', money: true },
                    { key: 'research_and_development', label: 'R&D', money: true },
                  ]} />
              </Section>
              <Section title="Balance sheet"
                right="quarterly · sec_edgar">
                <StatementTable
                  rows={detail.statements?.balance ?? []}
                  cols={[
                    { key: 'total_assets', label: 'Assets', money: true },
                    { key: 'cash_and_cash_equivalents', label: 'Cash', money: true },
                    { key: 'total_liabilities', label: 'Liab', money: true },
                    { key: 'long_term_debt', label: 'LT debt', money: true },
                    { key: 'total_shareholder_equity', label: 'Equity', money: true },
                  ]} />
              </Section>
              <Section title="Cash flow"
                right="quarterly · sec_edgar">
                <StatementTable
                  rows={detail.statements?.cash_flow ?? []}
                  cols={[
                    { key: 'operating_cash_flow', label: 'OCF', money: true },
                    { key: 'investing_cash_flow', label: 'ICF', money: true },
                    { key: 'financing_cash_flow', label: 'FCF fin', money: true },
                    { key: 'capital_expenditures', label: 'CapEx', money: true },
                    { key: 'free_cash_flow', label: 'FCF', money: true },
                  ]} />
              </Section>
            </div>
            <div className="space-y-4">
              <Section title="Categories"
                right={detail.health?.[0]?.period_end ?? ''}>
                <Categories row={detail.health?.[0] ?? {}} />
              </Section>
              <Section title="Ratios" right="sec_edgar">
                <StatementTable
                  rows={detail.statements?.ratios ?? []}
                  cols={[
                    { key: 'roe', label: 'ROE' },
                    { key: 'roic', label: 'ROIC' },
                    { key: 'gross_profit_margin', label: 'GP mgn' },
                    { key: 'net_profit_margin', label: 'Net mgn' },
                    { key: 'debt_to_equity', label: 'D/E' },
                  ]} />
              </Section>
              <Section title="Filings" right="EDGAR">
                <Filings rows={detail.filings ?? []} />
              </Section>
              <div className="rounded-xl border border-hairline bg-elevated/50 px-5 py-4 text-[11px] leading-relaxed text-faint">
                {detail.source ?? 'SEC EDGAR'} — consolidated facts as
                filed, amendments supersede by versioned journal. Scores
                are coverage-gated research signals, not investment
                recommendations.
              </div>
            </div>
          </div>
        </>
      ) : null}
    </main>
  )
}
