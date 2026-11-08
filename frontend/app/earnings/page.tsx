import Link from 'next/link'
import { api, type EarningsHighlight } from '@/lib/api'
import { Suspense } from 'react'
import { Section } from '@/components/regime'

function num(v: unknown) {
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

function money(v: unknown, dec = 2) {
  const n = Number(v)
  return Number.isFinite(n) ? `$${n.toFixed(dec)}` : '—'
}

function moneyShort(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const a = Math.abs(n)
  return a >= 1e9 ? `$${n.toFixed(2)}B`
    : a >= 1e6 ? `$${(n / 1e6).toFixed(0)}M` : `$${n.toFixed(0)}`
}

function pct(v: unknown, dec = 1, signed = true) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${signed && n >= 0 ? '+' : ''}${n.toFixed(dec)}%`
}

function pctTone(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n > 0 ? 'text-aggressive' : n < 0 ? 'text-defensive' : 'text-muted'
}

function verdictTone(v?: string) {
  return v === 'improving' ? 'text-aggressive border-aggressive/40'
    : v === 'deteriorating' ? 'text-defensive border-defensive/40'
      : 'text-caution border-caution/40'
}

function HlValue({ h }: { h: EarningsHighlight }) {
  const unit = h.unit === '%' ? '%' : h.unit === '$B' ? 'B' : ''
  const v = num(h.actual)
  const txt = v == null
    ? (h.actual != null ? String(h.actual) : '—')
    : unit === '%' ? `${v.toFixed(1)}%`
      : unit === 'B' ? moneyShort(v * 1e9)
        : money(v)
  return <span className="font-mono">{txt}</span>
}

function Consensus({ h }: { h: EarningsHighlight }) {
  const v = num(h.consensus)
  if (v == null && h.consensus == null) return <span className="text-faint">—</span>
  const unit = h.unit === '%' ? '%' : h.unit === '$B' ? 'B' : ''
  return (
    <span className="font-mono text-muted">
      {v == null ? String(h.consensus)
        : unit === 'B' ? moneyShort(v * 1e9)
          : unit === '%' ? `${v.toFixed(1)}%` : money(v)}
    </span>
  )
}

function Delta({ h }: { h: EarningsHighlight }) {
  const d = num(h.delta_pct)
  if (d == null) return <span className="text-faint">—</span>
  const label = d >= 3 ? 'beat' : d <= -3 ? 'miss' : 'in-line'
  return (
    <span className={`font-mono ${pctTone(d)}`}>
      {pct(d)} <span className="text-faint">({label})</span>
    </span>
  )
}

async function Report({
  sym, date, version,
}: { sym: string; date?: string; version?: number }) {
  const [rep, versions] = await Promise.all([
    api.earningsReport(sym, date, version),
    api.earningsReportVersions(sym),
  ])
  if (!rep?.report) {
    return (
      <div className="text-muted text-sm py-8">
        No earnings report for {sym} yet — the watcher journals one
        after the next print lands (16:00–20:00 ET polls).
      </div>
    )
  }
  const r = rep.report
  const priors = r.prior_prints ?? []
  const vs = versions?.versions ?? []
  const highlighted = num(r.print?.surprise_pct)

  return (
    <>
      {/* version strip */}
      {vs.length > 0 && (
        <div className="flex flex-wrap gap-2 text-[11px] font-mono pb-1">
          {vs.map(v => {
            const active = v.earnings_date === r.earnings_date
              && v.version === rep.version
            return (
              <Link
                key={`${v.earnings_date}-${v.version}`}
                href={`/earnings?sym=${sym}&date=${v.earnings_date}&version=${v.version}`}
                className={`rounded border px-2 py-0.5 ${
                  active
                    ? 'border-aggressive/50 text-aggressive'
                    : 'border-hairline text-muted hover:text-fg'}`}
              >
                {v.earnings_date} v{v.version}
              </Link>
            )
          })}
        </div>
      )}

      {/* headline */}
      <div className="pt-2">
        <h1 className="text-xl font-semibold leading-snug">
          {r.headline || rep.title}
        </h1>
        <div className="pt-2 flex flex-wrap items-center gap-3 text-xs font-mono text-muted">
          <span
            className={`rounded-full border px-2.5 py-0.5 font-semibold tracking-wider ${verdictTone(r.verdict)}`}
          >
            {r.verdict}
          </span>
          {r.thesis?.before && r.thesis.before !== r.thesis.after && (
            <span>
              thesis {r.thesis.before} → {r.thesis.after}
            </span>
          )}
          <span>reported {r.earnings_date}</span>
          {r.sector && <span>{r.sector}</span>}
          {r.market_cap_b != null && (
            <span>{moneyShort(Number(r.market_cap_b) * 1e9)} mcap</span>
          )}
          <span className="text-faint">
            v{rep.version} · {rep.generated_by}
          </span>
        </div>
      </div>

      {/* highlights — the vs-consensus table */}
      {(r.highlights ?? []).length > 0 && (
        <Section title={`${sym} ${r.quarter_label} highlights`}
                 defaultOpen>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-widest text-faint">
                <th className="pb-2 font-medium">metric</th>
                <th className="pb-2 font-medium text-right">actual</th>
                <th className="pb-2 font-medium text-right">consensus</th>
                <th className="pb-2 font-medium text-right">vs street</th>
              </tr>
            </thead>
            <tbody>
              {(r.highlights ?? []).map((h, i) => (
                <tr key={i} className="border-t border-hairline">
                  <td className="py-2 pr-3">
                    {h.metric}
                    {h.note && (
                      <span className="text-faint"> · {h.note}</span>
                    )}
                  </td>
                  <td className="py-2 text-right"><HlValue h={h} /></td>
                  <td className="py-2 text-right"><Consensus h={h} /></td>
                  <td className="py-2 text-right"><Delta h={h} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.print?.adjusted_eps_actual != null &&
            r.print.adjusted_eps_actual !== r.print.eps_actual && (
            <div className="pt-2 text-[11px] font-mono text-muted">
              adjusted EPS {money(r.print.adjusted_eps_actual)} ex
              one-time items — reported {money(r.print.eps_actual)}
              {r.print.one_time != null && ' (one-time charge noted)'}
            </div>
          )}
          {highlighted != null && (
            <div className="pt-1 text-[11px] font-mono text-muted">
              EPS surprise {pct(highlighted)}
              {r.print?.rev_surprise_pct != null &&
                ` · revenue surprise ${pct(r.print.rev_surprise_pct)}`}
            </div>
          )}
        </Section>
      )}

      {/* revenue growth */}
      {r.growth && (
        <Section title="Revenue growth" defaultOpen>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            {r.growth.quarter_yoy != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  this quarter YoY
                </div>
                <div className={`font-mono text-lg ${pctTone(r.growth.quarter_yoy)}`}>
                  {pct(r.growth.quarter_yoy)}
                </div>
              </div>
            )}
            {r.growth.two_year_ann != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  2y annualized
                </div>
                <div className={`font-mono text-lg ${pctTone(r.growth.two_year_ann)}`}>
                  {pct(r.growth.two_year_ann)}
                </div>
              </div>
            )}
            {r.growth.five_year_cagr != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  5y CAGR
                </div>
                <div className={`font-mono text-lg ${pctTone(r.growth.five_year_cagr)}`}>
                  {pct(r.growth.five_year_cagr)}
                </div>
              </div>
            )}
            {r.growth.forward_12m != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  street next 12m
                </div>
                <div className={`font-mono text-lg ${pctTone(r.growth.forward_12m)}`}>
                  {pct(r.growth.forward_12m)}
                </div>
              </div>
            )}
          </div>
          <div className="pt-3 text-xs text-muted leading-relaxed">
            {r.growth.quarter_yoy != null &&
              `${r.company_name || sym} grew revenue ${pct(r.growth.quarter_yoy, 1, false)}% year-on-year this quarter`}
            {r.growth.two_year_ann != null && r.growth.five_year_cagr != null &&
              ` — two-year annualized growth of ${pct(r.growth.two_year_ann, 1, false)}% ${
                r.growth.two_year_ann > r.growth.five_year_cagr
                  ? 'outpaces' : 'trails'
              } the five-year ${pct(r.growth.five_year_cagr, 1, false)}% CAGR`}
            {r.growth.forward_12m != null &&
              `. Analysts project ${pct(r.growth.forward_12m, 1, false)}% forward growth.`}
          </div>
        </Section>
      )}

      {/* quality — margins, cash conversion */}
      {r.quality && (
        <Section title="Quality — margins & cash">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            {[
              ['operating margin', r.quality.operating_margin,
               r.quality.operating_margin_yoy_pp],
              ['FCF margin', r.quality.fcf_margin,
               r.quality.fcf_margin_yoy_pp],
              ['net margin', r.quality.net_margin, null],
              ['gross margin', r.quality.gross_margin, null],
            ].map(([l, v, d]) => v != null && (
              <div key={String(l)}>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  {String(l)}
                </div>
                <div className="font-mono text-lg">
                  {num(v)!.toFixed(1)}%
                  {num(d) != null && (
                    <span className={`text-xs ${pctTone(d)}`}>
                      {' '}{pct(d, 1)}pp
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          {(r.quality.beat_streak != null ||
            r.quality.avg_surprise_pct != null) && (
            <div className="pt-3 text-xs font-mono text-muted">
              {r.quality.beat_streak != null &&
                `EPS beat streak ${r.quality.beat_streak}Q`}
              {r.quality.avg_surprise_pct != null &&
                ` · avg surprise ${pct(r.quality.avg_surprise_pct)}`}
            </div>
          )}
        </Section>
      )}

      {/* guidance drivers */}
      {(r.guidance_drivers ?? []).length > 0 && (
        <Section title="Guidance — named drivers" defaultOpen>
          <div className="space-y-2">
            {(r.guidance_drivers ?? []).map((d, i) => {
              const dir = String(d.delta_dir || 'new')
              const cp = num(d.consensus_pct)
              return (
                <div key={i}
                     className="flex flex-wrap items-baseline gap-x-3 text-sm border-b border-hairline/50 pb-2">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider ${
                      dir === 'raised' ? 'border-aggressive/40 text-aggressive'
                        : dir === 'cut' ? 'border-defensive/40 text-defensive'
                          : 'border-hairline text-muted'}`}
                  >
                    {dir}
                  </span>
                  <span className="font-medium">
                    {String(d.metric || '').replace(/_/g, ' ')}
                    {d.period ? ` ${d.period}` : ''}
                  </span>
                  <span className="font-mono">
                    {String(d.value_text || (num(d.value) != null ? moneyShort(num(d.value)) : '—'))}
                  </span>
                  {cp != null && (
                    <span className={`font-mono text-xs ${pctTone(cp)}`}>
                      {pct(cp)} vs street
                    </span>
                  )}
                  {d.quote != null && (
                    <span className="w-full text-xs text-faint italic">
                      “{String(d.quote).slice(0, 200)}”
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </Section>
      )}

      {/* expectations + stance */}
      {r.expectations && (
        <Section title="Forward expectations">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            {r.expectations.fwd_eps_avg != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  fwd EPS consensus
                </div>
                <div className="font-mono text-lg">
                  {money(r.expectations.fwd_eps_avg)}
                </div>
              </div>
            )}
            {r.expectations.fwd_rev_avg_b != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  fwd revenue consensus
                </div>
                <div className="font-mono text-lg">
                  {moneyShort(Number(r.expectations.fwd_rev_avg_b) * 1e9)}
                </div>
              </div>
            )}
            {r.expectations.fwd_pe != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  forward P/E
                </div>
                <div className="font-mono text-lg">
                  {Number(r.expectations.fwd_pe).toFixed(1)}×
                </div>
              </div>
            )}
            {r.expectations.gap_score != null && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-faint">
                  expectation gap
                </div>
                <div className="font-mono text-lg">
                  {Number(r.expectations.gap_score).toFixed(0)}
                  {r.expectations.muted_reaction && (
                    <span className="text-xs text-caution"> · muted</span>
                  )}
                </div>
              </div>
            )}
          </div>
          {r.expectations.est_revision_pct != null && (
            <div className="pt-2 text-xs font-mono text-muted">
              estimate revisions {pct(r.expectations.est_revision_pct)}
              {r.expectations.num_analysts != null &&
                ` · ${r.expectations.num_analysts} analysts`}
            </div>
          )}
          {r.expectations.stance_reason?.meaning && (
            <div className="pt-3 text-xs text-muted leading-relaxed border-t border-hairline mt-3">
              <span className="text-faint">stance — </span>
              {r.expectations.stance_reason.meaning}
              {r.expectations.stance_reason.because && (
                <div className="pt-1">
                  <span className="text-faint">because — </span>
                  {r.expectations.stance_reason.because}
                </div>
              )}
              {r.expectations.stance_reason.gaps && (
                <div className="pt-1">
                  <span className="text-faint">gaps — </span>
                  {r.expectations.stance_reason.gaps}
                </div>
              )}
            </div>
          )}
        </Section>
      )}

      {/* bounded LLM narrative */}
      {r.narrative && (
        <Section title="Analyst note">
          <p className="text-sm text-muted leading-relaxed whitespace-pre-line">
            {r.narrative}
          </p>
          <div className="pt-2 text-[10px] font-mono text-faint">
            grounded narrative — every number traced to journaled
            evidence
          </div>
        </Section>
      )}

      {/* takeaways */}
      {(r.takeaways ?? []).length > 0 && (
        <Section title={`Key takeaways — ${sym} ${r.quarter_label}`}
                 defaultOpen>
          <ul className="list-disc pl-5 space-y-1.5 text-sm text-muted">
            {(r.takeaways ?? []).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </Section>
      )}

      {/* bull / bear takeaways — verbatim claims partitioned by
          direction; LLM summary line only when the model produced
          one (deterministic lists always show) */}
      {r.bull_bear && ((r.bull_bear.bull ?? []).length > 0 ||
                       (r.bull_bear.bear ?? []).length > 0) && (
        <Section title="Bullish / bearish takeaway" defaultOpen>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { key: 'bull', label: 'Bullish takeaway', tone: 'text-aggressive' },
              { key: 'bear', label: 'Bearish takeaway', tone: 'text-defensive' },
            ].map(({ key, label, tone }) => {
              const items = (r.bull_bear as any)?.[key] ?? []
              const summary = (r.bull_bear as any)?.[`${key}_summary`]
              if (!items.length) return null
              return (
                <div key={key}>
                  <div className={`text-[11px] font-semibold uppercase tracking-wider ${tone}`}>
                    {label}
                  </div>
                  {summary && (
                    <p className="pt-1.5 text-sm text-ink">{summary}</p>
                  )}
                  <ul className="pt-1.5 list-disc pl-5 space-y-1 text-[12px] text-muted">
                    {items.map((t: string, i: number) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </Section>
      )}

      {/* prior prints */}
      {priors.length > 0 && (
        <Section title="Prior prints">
          <div className="space-y-1 text-sm font-mono">
            {priors.map((p, i) => {
              const s = num(p.surprise_percentage)
              return (
                <Link
                  key={i}
                  href={`/earnings?sym=${sym}&date=${p.earnings_date}`}
                  className="flex items-center gap-3 hover:text-fg text-muted">
                  <span>{p.earnings_date}</span>
                  {p.eps_actual != null && (
                    <span>EPS {money(p.eps_actual)}</span>
                  )}
                  {s != null && (
                    <span className={pctTone(s)}>{pct(s)}</span>
                  )}
                  {p.verdict && (
                    <span className={verdictTone(String(p.verdict)).split(' ')[0]}>
                      {String(p.verdict)}
                    </span>
                  )}
                  {p.report_version == null && (
                    <span className="text-faint text-[10px]">
                      no report
                    </span>
                  )}
                </Link>
              )
            })}
          </div>
        </Section>
      )}

      <div className="pt-4 text-[11px] font-mono text-faint">
        advisory only — deterministic composition from journaled
        evidence · <Link href={`/stock?sym=${sym}`}
                          className="underline hover:text-muted">
          back to {sym} stock page</Link>
      </div>
    </>
  )
}

async function Feed() {
  const feed = await api.earningsReportsFeed(60)
  const rows = feed?.reports ?? []
  if (!rows.length) {
    return (
      <div className="text-muted text-sm py-8">
        No earnings reports yet — reports journal automatically when
        book names print (earnings-watch, 16:00–20:00 ET).
      </div>
    )
  }
  return (
    <div className="space-y-1">
      {rows.map((r, i) => (
        <Link
          key={i}
          href={`/earnings?sym=${r.symbol}&date=${r.earnings_date}`}
          className="flex items-baseline gap-3 py-2 border-b border-hairline/50 hover:bg-white/[0.02]">
          <span className="font-mono font-semibold w-16">{r.symbol}</span>
          <span className="font-mono text-xs text-muted w-24">
            {r.earnings_date}
          </span>
          <span
            className={`text-[10px] font-semibold tracking-wider ${verdictTone(String(r.verdict || '')).split(' ')[0]}`}>
            {r.verdict}
          </span>
          <span className="text-xs text-muted truncate flex-1">
            {r.title}
          </span>
          <span className="font-mono text-[10px] text-faint">
            v{r.version}
          </span>
        </Link>
      ))}
    </div>
  )
}

export default async function EarningsPage({
  searchParams,
}: {
  searchParams: Promise<{ sym?: string; date?: string; version?: string }>
}) {
  const sp = await searchParams
  const sym = (sp.sym || '').toUpperCase()
  const version = sp.version ? Number(sp.version) : undefined
  return (
    <main className="mx-auto max-w-4xl px-4 pb-16">
      <div className="pt-8 pb-2 flex items-baseline justify-between">
        <h1 className="text-sm font-medium tracking-wide uppercase text-muted">
          {sym ? `Earnings report — ${sym}` : 'Earnings reports'}
        </h1>
        <Link href="/calendar"
              className="text-xs text-faint hover:text-muted font-mono">
          calendar →
        </Link>
      </div>
      <Suspense
        fallback={<div className="text-muted text-sm py-8">loading…</div>}>
        {sym
          ? <Report sym={sym} date={sp.date} version={version} />
          : <Feed />}
      </Suspense>
    </main>
  )
}
