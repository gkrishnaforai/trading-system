import Link from 'next/link'
import { api, type Receipt, type RegimeReceipt } from '@/lib/api'
import { Section, Stat } from '@/components/regime'

const ACTION_TONE: Record<string, string> = {
  EXIT: 'border-defensive/40 text-defensive',
  TRIM: 'border-caution/40 text-caution',
  PUT: 'border-defensive/40 text-defensive',
  BOUNCE: 'border-aggressive/40 text-aggressive',
  ACCUMULATE: 'border-aggressive/40 text-aggressive',
}

function Ret({ v }: { v?: number | null }) {
  if (v === null || v === undefined) {
    return <span className="text-faint">—</span>
  }
  const n = Number(v)
  return (
    <span
      className={`font-mono ${n > 0 ? 'text-aggressive' : n < 0 ? 'text-defensive' : 'text-muted'}`}
    >
      {n >= 0 ? '+' : ''}{n.toFixed(1)}
    </span>
  )
}

function ReceiptRow({ r }: { r: Receipt }) {
  const action = String(r.action ?? '—')
  const tone = ACTION_TONE[action] ?? 'border-hairline text-muted'
  const isLeaps = String(r.instrument ?? '').toUpperCase().includes('LEAPS')
  return (
    <tr className="border-t border-hairline/60 text-sm">
      <td className="py-2.5 pr-3 font-mono text-xs text-muted whitespace-nowrap">
        {r.as_of}
      </td>
      <td className="py-2.5 pr-3">
        <Link
          href={`/stock?sym=${encodeURIComponent(String(r.symbol ?? ''))}`}
          className="font-semibold text-ink hover:text-accent"
        >
          {r.symbol}
        </Link>
      </td>
      <td className="py-2.5 pr-3">
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wider ${tone}`}
        >
          {action}
        </span>
      </td>
      <td className="py-2.5 pr-3 text-xs text-muted whitespace-nowrap">
        {r.instrument ?? 'stock'}
      </td>
      <td className="py-2.5 pr-3 font-mono text-xs text-muted">
        {r.price != null ? `$${Number(r.price).toFixed(2)}` : '—'}
      </td>
      <td className="py-2.5 pr-2 text-right"><Ret v={r.r5} /></td>
      <td className="py-2.5 pr-2 text-right"><Ret v={r.r10} /></td>
      <td className="py-2.5 pr-2 text-right"><Ret v={r.r20} /></td>
      {isLeaps && <td className="py-2.5 pr-2 text-right"><Ret v={r.r60} /></td>}
      {!isLeaps && <td className="py-2.5 pr-2 text-right text-faint">·</td>}
    </tr>
  )
}

function RegimeRow({ r }: { r: RegimeReceipt }) {
  const graded = r.lead_correct !== null && r.lead_correct !== undefined
  return (
    <tr className="border-t border-hairline/60 text-sm">
      <td className="py-2.5 pr-3 font-mono text-xs text-muted">{r.as_of}</td>
      <td className="py-2.5 pr-3 text-muted">{r.stance ?? '—'}</td>
      <td className="py-2.5 pr-3 text-ink">{r.lead_scenario ?? '—'}</td>
      <td className="py-2.5 pr-2 text-right"><Ret v={r.spy_ret_20d} /></td>
      <td className="py-2.5 pr-2 text-right"><Ret v={r.spy_ret_60d} /></td>
      <td className="py-2.5 text-right">
        {!graded ? (
          <span className="text-faint">pending</span>
        ) : r.lead_correct ? (
          <span className="text-aggressive font-medium">✓</span>
        ) : (
          <span className="text-defensive font-medium">✗</span>
        )}
      </td>
    </tr>
  )
}

export default async function ReceiptsPage() {
  const data = await api.receipts(150)
  const decisions = data?.decisions ?? []
  const regime = data?.regime ?? []

  const graded20 = decisions.filter((d) => d.r20 !== null && d.r20 !== undefined)
  const hits20 = graded20.filter((d) => Number(d.r20) > 0).length
  const hitRate = graded20.length
    ? Math.round((100 * hits20) / graded20.length)
    : null
  const avg20 = graded20.length
    ? graded20.reduce((a, d) => a + Number(d.r20 ?? 0), 0) / graded20.length
    : null
  const gradedRegime = regime.filter(
    (r) => r.lead_correct !== null && r.lead_correct !== undefined,
  )
  const regimeHits = gradedRegime.filter((r) => r.lead_correct).length

  return (
    <main className="mx-auto max-w-4xl px-5 pb-20">
      <header className="pt-6 pb-8">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Receipts
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Every call, <span className="text-accent">graded.</span>
        </h1>
        <p className="pt-4 max-w-xl text-[15px] leading-relaxed text-muted">
          Each day&apos;s board picks are journaled at publish time and
          graded at fixed horizons — 5, 10 and 20 trading days (LEAPS to
          60). Wins and losses sit in the same list. This is the whole
          record, not the highlight reel.
        </p>
      </header>

      {graded20.length > 0 && (
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-6 rounded-xl border border-hairline bg-card px-5 py-4">
          <Stat label="Calls journaled" value={String(decisions.length)} />
          <Stat label="Graded at 20d" value={String(graded20.length)} />
          <Stat
            label="Hit rate @20d"
            value={hitRate != null ? `${hitRate}%` : '—'}
          />
          <Stat
            label="Avg return @20d"
            value={avg20 != null ? `${avg20 >= 0 ? '+' : ''}${avg20.toFixed(1)}%` : '—'}
          />
        </section>
      )}

      <Section title="Board calls" subtitle="journaled · graded" defaultOpen>
        {decisions.length === 0 ? (
          <p className="text-sm text-muted">
            The ledger is empty — board journaling writes each day&apos;s
            picks and the evaluator grades them at 5/10/20 sessions.
            Check back after the first graded window.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="pb-2 pr-3 font-medium">date</th>
                  <th className="pb-2 pr-3 font-medium">symbol</th>
                  <th className="pb-2 pr-3 font-medium">call</th>
                  <th className="pb-2 pr-3 font-medium">instrument</th>
                  <th className="pb-2 pr-3 font-medium">px</th>
                  <th className="pb-2 pr-2 font-medium text-right">5d</th>
                  <th className="pb-2 pr-2 font-medium text-right">10d</th>
                  <th className="pb-2 pr-2 font-medium text-right">20d</th>
                  <th className="pb-2 pr-2 font-medium text-right">60d</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((r) => (
                  <ReceiptRow key={r.id ?? `${r.as_of}-${r.symbol}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section
        title="Regime calls"
        subtitle={
          gradedRegime.length
            ? `${regimeHits}/${gradedRegime.length} lead scenarios correct`
            : 'lead scenario graded at 20d'
        }
        defaultOpen
      >
        {regime.length === 0 ? (
          <p className="text-sm text-muted">No regime snapshots yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="pb-2 pr-3 font-medium">date</th>
                  <th className="pb-2 pr-3 font-medium">stance</th>
                  <th className="pb-2 pr-3 font-medium">lead scenario</th>
                  <th className="pb-2 pr-2 font-medium text-right">SPY 20d</th>
                  <th className="pb-2 pr-2 font-medium text-right">SPY 60d</th>
                  <th className="pb-2 font-medium text-right">verdict</th>
                </tr>
              </thead>
              <tbody>
                {regime.map((r) => (
                  <RegimeRow key={r.as_of} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
        advisory — direction-adjusted returns vs the decision-day anchor;
        a PUT/EXIT scores positive when the name falls. No hindsight edits.
      </footer>
    </main>
  )
}
