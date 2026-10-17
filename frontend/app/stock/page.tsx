import Link from 'next/link'
import { api } from '@/lib/api'
import { Chip, Kv, Section, Stat } from '@/components/regime'

function money(v: unknown, dec = 2) {
  const n = Number(v)
  return Number.isFinite(n) ? `$${n.toFixed(dec)}` : '—'
}

function pct(v: unknown, dec = 1) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(dec)}%`
}

function pctTone(v: unknown) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 0 ? 'text-aggressive' : 'text-defensive'
}

function daysOld(d?: string | null) {
  if (!d) return null
  const t = Date.parse(d)
  if (!Number.isFinite(t)) return null
  return Math.max(0, Math.round((Date.now() - t) / 86400000))
}

function Fresh({ date }: { date?: string | null }) {
  const age = daysOld(date)
  if (age == null) return null
  const stale = age > 90
  return (
    <span
      className={`font-mono text-[11px] ${stale ? 'text-caution' : 'text-faint'}`}
    >
      {stale && '⚠ '}{String(date).slice(0, 10)} · {age}d old
    </span>
  )
}

function stateTone(s?: unknown) {
  const v = String(s ?? '').toLowerCase()
  if (['ready', 'confirmed', 'accelerating', 'healthy', 'improving', 'strong']
    .some((t) => v.includes(t))) return 'text-aggressive'
  if (['no', 'broken', 'blocked', 'deteriorating', 'broken_down', 'failed',
    'chase_block'].some((t) => v.includes(t))) return 'text-defensive'
  if (['close', 'watch', 'caution', 'stalling', 'mixed']
    .some((t) => v.includes(t))) return 'text-caution'
  return 'text-muted'
}

function obj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

export default async function StockPage({
  searchParams,
}: {
  searchParams: { sym?: string }
}) {
  const sym = (searchParams.sym ?? '').toUpperCase().trim()

  if (!sym) {
    return (
      <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
        <p className="text-sm text-muted">
          No symbol — open a stock from the{' '}
          <Link href="/board" className="text-accent underline">board</Link>.
        </p>
      </main>
    )
  }

  const card = await api.stockHealth(sym)
  if (!card) {
    return (
      <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
        <h1 className="font-semibold text-2xl">{sym}</h1>
        <p className="pt-3 text-sm text-muted">
          No data — symbol isn&apos;t on the book, or the worker is
          unreachable.
        </p>
      </main>
    )
  }

  const verdict = obj(card.verdict)
  const fv = obj(card.fv)
  const fvScen = obj(fv?.scenarios)
  const fvAnalyst = obj(fv?.analyst)
  const fvMethods = Array.isArray(fv?.methods) ? (fv!.methods as Record<string, unknown>[]) : []
  const fundamental = obj(card.fundamental)
  const technical = obj(card.technical)
  const sectorFlow = obj(card.sector_flow)
  const capex = obj(card.capex)
  const readiness = obj(card.readiness)
  const diagnosis = card.diagnosis
  const tailwinds = Array.isArray(card.tailwinds) ? card.tailwinds : []
  const themes = Array.isArray(card.themes) ? card.themes : []
  const upside = card.fv_upside_pct
  const earn = card.next_earnings ? String(card.next_earnings) : null
  const earnDays = earn ? daysOld(earn) !== null
    ? Math.round((Date.parse(earn) - Date.now()) / 86400000)
    : null : null

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <div className="pt-6 pb-2 text-xs">
        <Link href="/board" className="text-faint hover:text-accent">
          ← board
        </Link>
      </div>

      {/* hero */}
      <header className="pb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-semibold text-display text-ink">{sym}</h1>
          <div className="text-right">
            <div className="font-mono text-2xl text-ink">
              {money(card.spot)}
            </div>
            {upside != null && (
              <div className={`font-mono text-sm ${pctTone(upside)}`}>
                {pct(upside)} vs fair value
              </div>
            )}
          </div>
        </div>
        <div className="pt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted">
          {card.name != null && <span>{String(card.name)}</span>}
          {card.sector != null && (
            <span className="text-faint">· {String(card.sector)}</span>
          )}
          {card.market_cap != null && (
            <span className="font-mono text-xs text-faint">
              ${(Number(card.market_cap) / 1e9).toFixed(1)}B
            </span>
          )}
          {sectorFlow?.flow != null && (
            <span
              className={`text-xs ${String(sectorFlow.flow).includes('out')
                ? 'text-defensive'
                : String(sectorFlow.flow).includes('in')
                  ? 'text-aggressive'
                  : 'text-muted'
                }`}
            >
              {String(sectorFlow.etf)} {String(sectorFlow.flow)}
              {sectorFlow.score != null && ` ${sectorFlow.score}`}
            </span>
          )}
          {earnDays != null && earnDays >= 0 && earnDays <= 14 && (
            <span className="text-xs text-caution">
              ⚠ earnings in {earnDays}d ({earn})
            </span>
          )}
        </div>
      </header>

      {/* the call */}
      {verdict && (
        <section className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              The call
            </span>
            {verdict.verdict != null && (
              <span className={`text-sm font-medium ${stateTone(verdict.verdict)}`}>
                {String(verdict.verdict)}
              </span>
            )}
          </div>
          {Array.isArray(verdict.why) && verdict.why.length > 0 && (
            <ul className="pt-3 space-y-1 text-sm text-muted leading-relaxed">
              {(verdict.why as unknown[]).slice(0, 6).map((w, i) => (
                <li key={i}>· {String(w)}</li>
              ))}
            </ul>
          )}
          {diagnosis != null && (
            <p className="pt-3 border-t border-hairline/60 mt-3 text-xs text-muted">
              {typeof diagnosis === 'object'
                ? JSON.stringify(diagnosis)
                : String(diagnosis)}
            </p>
          )}
        </section>
      )}

      {/* readiness lanes */}
      {readiness && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Readiness
          </div>
          <div className="pt-3 flex flex-wrap gap-2">
            {Object.entries(readiness).map(([lane, v]) => {
              const r = obj(v)
              const state = r?.state ?? r?.readiness ?? v
              return (
                <span
                  key={lane}
                  className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1 text-xs ${stateTone(state)}`}
                >
                  <span className="text-muted">{lane.replace(/_/g, ' ')}</span>
                  {String(state)}
                </span>
              )
            })}
          </div>
        </section>
      )}

      {/* fair value */}
      {fv && (
        <section className="mt-2 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
              Fair value
            </span>
            <div className="flex gap-3 items-baseline">
              <Fresh date={fv.as_of ? String(fv.as_of) : null} />
              {fv.fundamentals_as_of != null && (
                <span className="font-mono text-[11px] text-faint">
                  inputs{' '}
                  <Fresh date={String(fv.fundamentals_as_of)} />
                </span>
              )}
            </div>
          </div>
          <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-6">
            <Stat label="Spot" value={money(card.spot ?? fv.spot)} />
            <Stat label="Expected FV" value={money(fv.expected)} />
            {fvScen?.bear != null && (
              <Stat label="Bear" value={money(fvScen.bear)} />
            )}
            {fvScen?.bull != null && (
              <Stat label="Bull" value={money(fvScen.bull)} />
            )}
          </div>
          {fvScen?.base != null && (
            <div className="pt-3 text-xs text-muted font-mono">
              base {money(fvScen.base)}
              {fv.regime != null && ` · regime ${String(fv.regime)}`}
              {fv.spot_at_run != null &&
                Number(fv.spot_at_run) !== Number(card.spot) &&
                ` · spot at run ${money(fv.spot_at_run)}`}
            </div>
          )}
          {Array.isArray(fv.flags) && fv.flags.length > 0 && (
            <div className="pt-3 flex flex-wrap gap-2">
              {(fv.flags as unknown[]).map((f, i) => (
                <Chip key={i} label={String(f)} tone="warn" />
              ))}
            </div>
          )}
          {fvAnalyst && (
            <p className="pt-3 text-xs text-faint">
              street: {money(fvAnalyst.consensus_price_target)}
              {fvAnalyst.price_target_low != null &&
                ` (${money(fvAnalyst.price_target_low)}–${money(fvAnalyst.price_target_high)})`}
              {fvAnalyst.analyst_count != null &&
                ` · ${String(fvAnalyst.analyst_count)} analysts`}
              {' — context, not the blend'}
            </p>
          )}
        </section>
      )}

      {/* fundamentals + technical + capex strip */}
      <section className="mt-2 grid sm:grid-cols-3 gap-2">
        <div className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Fundamentals
          </div>
          <div className={`pt-2 text-sm font-medium ${stateTone(fundamental?.state)}`}>
            {String(fundamental?.state ?? '—')}
          </div>
          {fundamental?.risk != null && (
            <div className="pt-1 text-xs text-muted">
              risk {String(fundamental.risk)}
            </div>
          )}
          <div className="pt-2 space-y-1">
            <Fresh date={fundamental?.data_as_of ? String(fundamental.data_as_of) : null} />
            {fundamental?.as_of != null && (
              <div className="font-mono text-[11px] text-faint">
                scored {String(fundamental.as_of).slice(0, 10)}
              </div>
            )}
          </div>
        </div>
        <div className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Tape
          </div>
          <div className={`pt-2 text-sm font-medium ${stateTone(technical?.state)}`}>
            {String(technical?.state ?? '—')}
          </div>
          {technical?.as_of != null && (
            <div className="pt-2 font-mono text-[11px] text-faint">
              {String(technical.as_of).slice(0, 10)}
            </div>
          )}
        </div>
        <div className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            AI capex
          </div>
          {capex ? (
            <>
              <div className="pt-2 text-sm font-medium text-ink">
                {String(capex.exposure ?? capex.bucket ?? capex.category ?? 'tracked')}
              </div>
              <div className="pt-1 text-xs text-muted">
                cycle {String(capex.band ?? '—')}
                {capex.score != null && ` ${String(capex.score)}/100`}
              </div>
            </>
          ) : (
            <div className="pt-2 text-sm text-muted">not in a capex basket</div>
          )}
        </div>
      </section>

      {/* expandable depth */}
      <div className="mt-8">
        {fvMethods.length > 0 && (
          <Section title="Valuation methods" subtitle={`${fvMethods.length} blended`}>
            <div className="divide-y divide-transparent">
              {fvMethods.map((m, i) => (
                <Kv
                  key={i}
                  k={String(m.key ?? 'method') +
                    (m.w != null ? ` (w ${Number(m.w).toFixed(2)})` : '')}
                  v={money(m.fv)}
                />
              ))}
            </div>
          </Section>
        )}

        {(tailwinds.length > 0 || themes.length > 0) && (
          <Section title="Tailwinds & themes">
            <div className="flex flex-wrap gap-2">
              {tailwinds.slice(0, 12).map((t, i) => (
                <Chip key={`t${i}`} label={String(typeof t === 'object' ? JSON.stringify(t) : t)} tone="ok" />
              ))}
              {themes.slice(0, 12).map((t, i) => (
                <Chip key={`h${i}`} label={String(typeof t === 'object' ? JSON.stringify(t) : t)} />
              ))}
            </div>
          </Section>
        )}

        {fundamental?.detail != null && (
          <Section title="Fundamentals detail">
            <div className="divide-y divide-transparent">
              {Object.entries(obj(fundamental.detail) ?? {}).slice(0, 24).map(([k, v]) => (
                <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
              ))}
            </div>
          </Section>
        )}

        {technical?.detail != null && (
          <Section title="Tape detail">
            <div className="divide-y divide-transparent">
              {Object.entries(obj(technical.detail) ?? {}).slice(0, 24).map(([k, v]) => (
                <Kv key={k} k={k.replace(/_/g, ' ')} v={v} />
              ))}
            </div>
          </Section>
        )}
      </div>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — evidence assembled, human decides</span>
        <span className="font-mono">{sym}</span>
      </footer>
    </main>
  )
}
