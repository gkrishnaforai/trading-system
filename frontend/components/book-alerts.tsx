import type { AlertItem } from '@/lib/api'
import Link from 'next/link'

const DIR: Record<string, string> = {
  POSITIVE: 'text-aggressive',
  UP: 'text-aggressive',
  NEGATIVE: 'text-defensive',
  DOWN: 'text-defensive',
}

function fmtDetail(d?: Record<string, unknown>): string[] {
  if (!d) return []
  const out: string[] = []
  const t = d.thesis as Record<string, unknown> | undefined
  if (t?.before || t?.after)
    out.push(`thesis ${t?.before ?? 'new'} → ${t?.after ?? '?'}`)
  const v = d.veto as Record<string, unknown> | undefined
  if (v?.flag) out.push(`veto: ${String(v.flag)}`)
  for (const k of ['note', 'reason', 'verdict', 'quote', 'metric'])
    if (d[k]) out.push(`${k}: ${String(d[k]).slice(0, 180)}`)
  const b = d.buy as Record<string, unknown> | undefined
  if (b?.insiders) out.push(`insiders: ${(b.insiders as string[]).join(', ')}`)
  return out.slice(0, 5)
}

/** Latest alerts for a book's symbols — expandable in place so the
 *  action (read detail, jump to the stock) is on the same screen. */
export function BookAlerts({ items, symbols }: {
  items?: AlertItem[]; symbols: Set<string>
}) {
  const mine = (items ?? [])
    .filter((a) => a.symbol && symbols.has(a.symbol))
    .slice(0, 12)
  if (!mine.length) return null
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Book alerts · latest
        </span>
        <span className="font-mono text-[11px] text-faint">
          {mine.length} · expand a row
        </span>
      </div>
      <div className="mt-2 divide-y divide-hairline/60">
        {mine.map((a, i) => (
          <details key={a.id ?? i} className="group py-2">
            <summary className="flex cursor-pointer items-baseline gap-3 list-none">
              <Link
                href={`/stock?sym=${encodeURIComponent(a.symbol!)}`}
                className="w-14 shrink-0 font-mono text-[12px] font-semibold text-accent hover:underline"
              >
                {a.symbol}
              </Link>
              <span
                className={`w-16 shrink-0 font-mono text-[10px] uppercase ${DIR[a.direction ?? ''] ?? 'text-muted'}`}
              >
                {a.direction ?? '—'} {a.materiality === 'HIGH' ? '·HIGH' : ''}
              </span>
              <span className="min-w-0 flex-1 truncate text-[12px] text-ink">
                {a.title}
              </span>
              <span className="text-faint select-none group-open:rotate-90 transition-transform">
                ›
              </span>
            </summary>
            <div className="pl-[7.5rem] pt-2 space-y-1">
              <p className="font-mono text-[10px] text-faint">
                {a.event_type?.replace(/_/g, ' ')} · {a.source ?? 'engine'} ·{' '}
                {a.created_at ? new Date(a.created_at).toLocaleString('en-US', {
                  month: 'short', day: 'numeric', hour: 'numeric',
                  minute: '2-digit', timeZone: 'America/New_York',
                }) + ' ET' : ''}
              </p>
              {fmtDetail(a.detail).map((l, j) => (
                <p key={j} className="text-[11px] leading-relaxed text-muted">
                  · {l}
                </p>
              ))}
              <Link
                href={`/stock?sym=${encodeURIComponent(a.symbol!)}`}
                className="inline-block pt-1 text-[11px] text-accent hover:underline"
              >
                open {a.symbol} detail →
              </Link>
            </div>
          </details>
        ))}
      </div>
    </section>
  )
}
