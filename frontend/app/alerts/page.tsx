import Link from 'next/link'
import { api, type AlertItem } from '@/lib/api'
import { fmtShort } from '@/components/regime'
import { ScanButton } from '@/components/scan-button'

const DIR_TONE: Record<string, string> = {
  positive: 'text-aggressive', up: 'text-aggressive',
  bullish: 'text-aggressive',
  negative: 'text-defensive', down: 'text-defensive',
  bearish: 'text-defensive',
  neutral: 'text-muted',
}

const MAT_TONE: Record<string, string> = {
  high: 'border-defensive/40 text-defensive',
  medium: 'border-caution/40 text-caution',
  low: 'border-hairline text-muted',
}

function ago(ts?: string) {
  if (!ts) return ''
  const t = Date.parse(ts)
  if (!Number.isFinite(t)) return ''
  const m = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (m < 60) return `${m}m ago`
  if (m < 1440) return `${Math.round(m / 60)}h ago`
  return `${Math.round(m / 1440)}d ago`
}

function AlertRow({ a }: { a: AlertItem }) {
  const dir = String(a.direction ?? 'neutral').toLowerCase()
  const mat = String(a.materiality ?? 'low').toLowerCase()
  const isEarnings = ['earnings', 'guidance'].includes(
    String(a.event_type ?? '').toLowerCase())
  const det =
    typeof a.detail === 'object' && a.detail !== null
      ? (a.detail as Record<string, unknown>)
      : null
  const verdict = det?.verdict ? String(det.verdict) : null
  return (
    <div className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {a.symbol && (
              <Link
                href={`/stock?sym=${encodeURIComponent(a.symbol)}`}
                className="font-semibold text-ink hover:text-accent"
              >
                {a.symbol}
              </Link>
            )}
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${MAT_TONE[mat] ?? MAT_TONE.low}`}
            >
              {a.materiality ?? 'low'}
            </span>
            {a.event_type && (
              <span
                className={
                  isEarnings
                    ? 'rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent'
                    : 'rounded-full bg-elevated px-2 py-0.5 text-[10px] text-muted'
                }
              >
                {String(a.event_type).replace(/_/g, ' ')}
              </span>
            )}
            {isEarnings && verdict && (
              <span
                className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${verdict === 'improving'
                  ? 'border-aggressive/40 text-aggressive'
                  : verdict === 'deteriorating'
                    ? 'border-defensive/40 text-defensive'
                    : 'border-caution/40 text-caution'
                  }`}
              >
                {verdict}
              </span>
            )}
            {a.in_portfolio && (
              <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
                held
              </span>
            )}
            {a.in_watchlist && (
              <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[10px] text-accent">
                ★
              </span>
            )}
          </div>
          <div className={`pt-1 text-sm ${DIR_TONE[dir] ?? 'text-ink'}`}>
            {a.title ?? '—'}
          </div>
          {a.detail != null && (
            <div className="pt-0.5 text-xs text-muted">
              {fmtShort(a.detail).slice(0, 220)}
            </div>
          )}
          {a.rating_action && (
            <div className="pt-0.5 text-[11px] text-faint">
              {a.rating_action}
            </div>
          )}
        </div>
        <div className="shrink-0 text-right font-mono text-[11px] text-faint">
          {ago(a.created_at)}
          {a.priority_score != null && (
            <div>p{Number(a.priority_score).toFixed(0)}</div>
          )}
        </div>
      </div>
    </div>
  )
}

export default async function AlertsPage() {
  const data = await api.alerts({ hours: 168 })
  const items = data?.items ?? []
  const scan = (data as { scan?: { running?: boolean } } | null)?.scan
  const newItems = items.filter((a) => a.status !== 'dismissed')
  const high = newItems.filter(
    (a) => String(a.materiality).toLowerCase() === 'high',
  )

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-8">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Alert inbox
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          What moved <span className="text-accent">on the book.</span>
        </h1>
        <p className="pt-4 max-w-xl text-[15px] leading-relaxed text-muted">
          Catalyst events ranked by materiality — ratings, earnings,
          filings, momentum breaks — filtered to the names you hold and
          watch. Held names get the orange badge.
        </p>
        <div className="pt-4">
          <ScanButton running={scan?.running ?? false} />
        </div>
      </header>

      <section className="grid grid-cols-3 gap-6 rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-faint">
            This week
          </div>
          <div className="mt-1 font-mono text-lg text-ink">
            {newItems.length}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-faint">
            High materiality
          </div>
          <div className="mt-1 font-mono text-lg text-defensive">
            {high.length}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-faint">
            On held names
          </div>
          <div className="mt-1 font-mono text-lg text-accent">
            {newItems.filter((a) => a.in_portfolio).length}
          </div>
        </div>
      </section>

      <div className="border-t border-hairline">
        {newItems.length === 0 ? (
          <p className="py-8 text-sm text-muted">
            {scan?.running
              ? 'Scanning for catalysts — refresh in a moment.'
              : 'Quiet week — no undismissed alerts in the last 7 days. A scan may be running in the background.'}
          </p>
        ) : (
          <div className="divide-y divide-hairline/60">
            {newItems.map((a, i) => (
              <AlertRow key={a.id ?? i} a={a} />
            ))}
          </div>
        )}
      </div>

      <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
        advisory — events, not instructions. Same alert feed the
        scheduler scans; a per-stock slice lives on each stock page.
      </footer>
    </main>
  )
}
