import { api } from '@/lib/api'
import { ReserveTracker, CrashPlaybook } from '@/components/hold'
import Link from 'next/link'

export const dynamic = 'force-dynamic'

const TONE: Record<string, { ring: string; text: string; label: string }> = {
  aggressive: { ring: 'border-aggressive/60 bg-aggressive/[0.06]', text: 'text-aggressive', label: 'green light' },
  caution: { ring: 'border-caution/60 bg-caution/[0.06]', text: 'text-caution', label: 'caution' },
  defensive: { ring: 'border-defensive/60 bg-defensive/[0.06]', text: 'text-defensive', label: 'defensive' },
}

function WRow({ k, base, tilt }: { k: string; base: number; tilt: number }) {
  const d = tilt - base
  return (
    <div className="grid grid-cols-[52px_1fr_70px] items-center gap-3 py-1">
      <span className="font-mono text-[13px] font-semibold text-ink">{k}</span>
      <div className="relative h-[7px] rounded-full bg-hairline">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-faint/50"
          style={{ width: `${base}%` }}
        />
        <div
          className="absolute -top-[2px] h-[11px] w-[3px] rounded-full bg-accent"
          style={{ left: `calc(${Math.min(100, tilt)}% - 1px)` }}
        />
      </div>
      <span className={`font-mono text-[12px] text-right ${d > 0 ? 'text-aggressive' : d < 0 ? 'text-defensive' : 'text-muted'}`}>
        {d > 0 ? '+' : ''}{d.toFixed(0)}pts → {tilt}%
      </span>
    </div>
  )
}

export default async function HoldPage() {
  const d = await api.passive()
  const v = d?.verdict ?? {}
  const t = TONE[v.tone ?? 'caution'] ?? TONE.caution
  const book = d?.book
  const ctx = d?.context
  const weights = Object.keys(book?.tilt ?? book?.base ?? {})

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
      <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-accent">
        For the boring money
      </p>
      <h1 className="mt-2 text-display font-semibold tracking-tight text-ink">
        Hold. Monthly, not daily.
      </h1>
      <p className="mt-3 max-w-xl text-[14.5px] leading-relaxed text-muted">
        One decision a month for a passive book: buy as planned, split
        it, or hold the contribution in reserve. The same regime engine
        the desk uses — minus the noise.
      </p>

      {/* monthly verdict */}
      <section className={`mt-8 rounded-xl border px-5 py-5 ${t.ring}`}>
        <div className="flex items-baseline justify-between">
          <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
            This month's verdict
          </span>
          <span className={`text-[11px] font-semibold uppercase tracking-wider ${t.text}`}>
            {t.label}
          </span>
        </div>
        <h2 className={`pt-2 text-[22px] font-semibold tracking-tight ${t.text}`}>
          {v.headline ?? 'No read yet — the morning regime has not journaled.'}
        </h2>
        {v.note && (
          <p className="pt-2 max-w-lg text-[13.5px] leading-relaxed text-muted">
            {v.note}
          </p>
        )}
        <div className="pt-3 font-mono text-[11px] text-faint">
          posture {d?.posture ?? '—'}
          {d?.matched ? ` · rule ${d.matched}` : ''}
          {d?.as_of ? ` · regime ${String(d.as_of).slice(0, 10)}` : ''}
        </div>
      </section>

      {/* reserve + playbook */}
      <section className="mt-2 grid gap-2 sm:grid-cols-2">
        <ReserveTracker action={v.action} />
        <CrashPlaybook
          defensive={(d?.posture ?? '').toLowerCase().includes('defens')}
        />
      </section>

      {/* model ETF book */}
      {book && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Model book — {book.name}
            </span>
            <span className="font-mono text-[11px] text-faint">
              bar = base · marker = suggested
            </span>
          </div>
          {book.note && (
            <p className="pt-2 max-w-lg text-[12.5px] leading-relaxed text-muted">
              {book.note}
            </p>
          )}
          <div className="pt-3">
            {weights.map((k) => (
              <WRow
                key={k}
                k={k}
                base={Number((book.base ?? {})[k] ?? 0)}
                tilt={Number((book.tilt ?? {})[k] ?? 0)}
              />
            ))}
          </div>
          {book.reason && (
            <p className="pt-3 border-t border-hairline/60 mt-3 text-[12.5px] leading-relaxed text-muted">
              {book.reason}
            </p>
          )}
          <p className="pt-2 text-[11px] text-faint">
            Suggestions are journaled daily and graded later —{' '}
            <Link href="/receipts" className="text-accent underline decoration-accent/30">
              receipts
            </Link>{' '}
            show the record, misses included. We never touch your account.
          </p>
          {(d?.tilt_history ?? []).length > 0 && (
            <div className="pt-3">
              <div className="text-[10px] uppercase tracking-wider text-faint">
                recent suggestions
              </div>
              <div className="pt-1 flex flex-wrap gap-1.5">
                {(d?.tilt_history ?? []).slice(0, 10).map((h, i) => (
                  <span
                    key={i}
                    className={`rounded border px-1.5 py-0.5 font-mono text-[10.5px] ${(h.posture ?? '').toLowerCase().includes('defens')
                      ? 'border-defensive/40 text-defensive'
                      : (h.posture ?? '').toLowerCase().includes('aggress')
                        ? 'border-aggressive/40 text-aggressive'
                        : 'border-hairline text-muted'
                      }`}
                    title={h.reason ?? ''}
                  >
                    {h.as_of} {h.posture}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* drawdown context */}
      {ctx && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Why the tape looks scary — and why that's normal
          </div>
          <div className="pt-3 grid grid-cols-3 gap-4">
            <div>
              <div className="font-mono text-lg text-ink">
                {ctx.spy_vs_200 != null
                  ? `${(Number(ctx.spy_vs_200) * 100).toFixed(1)}%`
                  : '—'}
              </div>
              <div className="text-[11px] text-faint">SPY vs 200dma</div>
            </div>
            <div>
              <div className="font-mono text-lg text-ink">
                {ctx.dip_character ?? '—'}
              </div>
              <div className="text-[11px] text-faint">dip character</div>
            </div>
            <div>
              <div className="font-mono text-lg text-ink">
                {ctx.lead_scenario ?? '—'}
              </div>
              <div className="text-[11px] text-faint">lead scenario</div>
            </div>
          </div>
          {ctx.verdict_line && (
            <p className="pt-3 text-[13px] leading-relaxed text-muted">
              {ctx.verdict_line}
            </p>
          )}
        </section>
      )}

      <p className="mt-10 text-center text-[12px] text-faint">
        Advisory only. The second opinion your broker is paid not to
        give you — we never touch the account.
      </p>
    </main>
  )
}
