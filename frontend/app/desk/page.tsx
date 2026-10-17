import Link from 'next/link'
import { api } from '@/lib/api'
import { Chip, Section, Stat, Val, fmtShort } from '@/components/regime'
import { Gate } from '@/components/regime'

function obj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

function arr(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v)
    ? (v.filter((x) => x && typeof x === 'object') as Record<string, unknown>[])
    : []
}

function num(v: unknown): number | null {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function Sym({ s }: { s: unknown }) {
  const t = String(s ?? '')
  if (!t) return <span className="text-faint">—</span>
  return (
    <Link
      href={`/stock?sym=${encodeURIComponent(t)}`}
      className="font-semibold text-ink hover:text-accent"
    >
      {t}
    </Link>
  )
}

function Pct({ v }: { v: unknown }) {
  const n = num(v)
  if (n === null) return <span className="text-faint">—</span>
  return (
    <span
      className={`font-mono ${n > 0 ? 'text-aggressive' : n < 0 ? 'text-defensive' : 'text-muted'}`}
    >
      {n >= 0 ? '+' : ''}{n.toFixed(1)}
    </span>
  )
}

function SubNav() {
  const items = [
    ['#planner', 'Planner'], ['#conviction', 'Conviction'],
    ['#screens', 'Screens'], ['#expressions', 'Expressions'],
  ] as const
  return (
    <div className="sticky top-[57px] z-10 -mx-5 border-b border-hairline bg-canvas/90 px-5 backdrop-blur">
      <div className="flex gap-1 py-2">
        {items.map(([href, label]) => (
          <a
            key={href}
            href={href}
            className="rounded-full px-3 py-1 text-[12px] font-medium text-muted hover:bg-elevated hover:text-accent transition-colors"
          >
            {label}
          </a>
        ))}
      </div>
    </div>
  )
}

/* ---------------- planner ---------------- */

function PlannerSection({ s }: { s: Record<string, unknown> | null }) {
  const morning = obj(s?.morning)
  const direction = obj(s?.direction)
  const weights = obj(s?.weights)
  const current = obj(s?.current)
  const playbook = s?.playbook
  const themes = s?.themes
  const earnings = obj(s?.earnings)

  // flatten {sym: weight} or {sym: {target: x}} shapes into rows
  const rows = Object.entries(weights ?? {}).map(([sym, v]) => {
    const o = obj(v)
    const target = num(o?.target ?? o?.weight ?? v)
    const cur = num(obj(current?.[sym])?.weight ?? current?.[sym])
    return { sym, target, cur, delta: target != null && cur != null ? target - cur : null }
  }).sort((a, b) => (b.target ?? 0) - (a.target ?? 0))

  return (
    <section id="planner" className="scroll-mt-24 pt-8">
      <div className="flex items-baseline justify-between pb-4">
        <h2 className="text-lg font-semibold text-ink">
          Planner <span className="text-accent">·</span>{' '}
          <span className="text-sm font-normal text-muted">
            where the book should point
          </span>
        </h2>
        {morning?.regime != null && (
          <span className="font-mono text-xs text-faint">
            regime {String(morning.regime)}
            {morning.score != null && ` ${String(morning.score)}`}
          </span>
        )}
      </div>

      {direction && (
        <div className="rounded-xl border border-hairline bg-card px-5 py-4 mb-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-2">
            Money rotation
          </div>
          <Val v={direction} />
        </div>
      )}

      {rows.length > 0 && (
        <div className="rounded-xl border border-hairline bg-card px-5 py-4 mb-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-3">
            Target weights vs book
          </div>
          <div className="space-y-1.5">
            {rows.slice(0, 14).map((r) => (
              <div key={r.sym} className="flex items-center gap-3 text-sm">
                <span className="w-16"><Sym s={r.sym} /></span>
                <div className="flex-1 h-1.5 rounded-full bg-elevated overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent/70"
                    style={{ width: `${Math.min(100, Math.max(0, r.target ?? 0))}%` }}
                  />
                </div>
                <span className="w-12 text-right font-mono text-xs text-ink">
                  {r.target != null ? `${r.target.toFixed(0)}%` : '—'}
                </span>
                <span className="w-12 text-right font-mono text-xs text-muted">
                  {r.cur != null ? `${r.cur.toFixed(0)}%` : '—'}
                </span>
                <span className="w-12 text-right font-mono text-xs">
                  <Pct v={r.delta} />
                </span>
              </div>
            ))}
          </div>
          <div className="pt-2 flex justify-end gap-6 text-[10px] text-faint font-mono">
            <span>target · book · Δ</span>
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-3">
        {playbook != null && (
          <div className="rounded-xl border border-hairline bg-card px-5 py-4">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-2">
              Playbook
            </div>
            <Val v={playbook} />
          </div>
        )}
        {earnings && Object.keys(earnings).length > 0 && (
          <div className="rounded-xl border border-hairline bg-card px-5 py-4">
            <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-2">
              Earnings concentration
            </div>
            <Val v={earnings} />
          </div>
        )}
      </div>
      {themes != null && (
        <Section title="Theme scores" subtitle="rotation × regime">
          <Val v={themes} depth={1} />
        </Section>
      )}
    </section>
  )
}

/* ---------------- conviction ---------------- */

function ConvictionSection({ c }: { c: Record<string, unknown> | null }) {
  const list = arr(c?.the_list)
  const watch = arr(c?.watch)
  const daily = arr(c?.daily_picks)
  const weekly = obj(c?.weekly_pick)
  const monthly = arr(c?.monthly_picks)

  return (
    <section id="conviction" className="scroll-mt-24 pt-10 border-t border-hairline mt-10">
      <h2 className="text-lg font-semibold text-ink pb-4">
        Conviction <span className="text-accent">·</span>{' '}
        <span className="text-sm font-normal text-muted">
          the meta-engine&apos;s top names
        </span>
      </h2>

      <div className="flex flex-wrap gap-2 pb-4">
        {daily.map((d, i) => (
          <span key={`d${i}`} className="rounded-full bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
            daily · <Sym s={d.symbol} />
          </span>
        ))}
        {weekly?.symbol != null && (
          <span className="rounded-full bg-aggressive/10 px-3 py-1 text-xs font-medium text-aggressive">
            weekly · <Sym s={weekly.symbol} />
          </span>
        )}
        {monthly.map((m, i) => (
          <span key={`m${i}`} className="rounded-full border border-aggressive/40 px-3 py-1 text-xs font-medium text-aggressive">
            monthly · <Sym s={m.symbol} />
          </span>
        ))}
      </div>

      {list.length > 0 && (
        <div className="rounded-xl border border-hairline bg-card px-5 py-2 mb-3">
          <div className="divide-y divide-hairline/60">
            {list.slice(0, 15).map((r, i) => (
              <div key={i} className="py-2.5 flex items-center gap-3 text-sm">
                <span className="w-6 font-mono text-xs text-faint">
                  {String(r.rank ?? i + 1)}
                </span>
                <span className="w-16"><Sym s={r.symbol} /></span>
                <span className="w-12 font-mono text-xs text-ink">
                  {r.score != null ? String(r.score) : ''}
                </span>
                {r.momentum_state != null && (
                  <span className="text-xs text-muted">
                    {String(r.momentum_state)}
                  </span>
                )}
                <span className="flex-1 text-xs text-muted truncate">
                  {fmtShort(r.themes ?? r.sources ?? r.parts).slice(0, 90)}
                </span>
                {r.fwd_pe != null && (
                  <span className="font-mono text-[11px] text-faint">
                    {String(r.fwd_pe)}×
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {watch.length > 0 && (
        <div className="rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint pb-2">
            Watch lane — future compounders
          </div>
          <div className="flex flex-wrap gap-2">
            {watch.map((w, i) => (
              <Chip
                key={i}
                label={`${String(w.symbol ?? '')}${w.future_score != null ? ` ${String(w.future_score)}` : ''}`}
              />
            ))}
          </div>
        </div>
      )}
      {!c && (
        <p className="text-sm text-muted">Conviction engine returned nothing.</p>
      )}
    </section>
  )
}

/* ---------------- screens ---------------- */

function ScreenTable({ rows, cols }: {
  rows: Record<string, unknown>[]
  cols: [string, string][]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-faint">
            {cols.map(([k, label]) => (
              <th key={k} className="pb-2 pr-4 font-medium">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 15).map((r, i) => (
            <tr key={i} className="border-t border-hairline/60">
              {cols.map(([k], j) => (
                <td key={k} className="py-2 pr-4">
                  {k === 'symbol' ? (
                    <Sym s={r[k]} />
                  ) : (
                    <span className="text-muted font-mono text-xs">
                      {fmtShort(r[k]).slice(0, 60)}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ScreensSection({ gems, cats }: {
  gems: Record<string, unknown> | null
  cats: Record<string, unknown> | null
}) {
  const gemRows = arr(gems?.rows ?? gems?.items ?? gems?.list)
  const changes = obj(gems?.changes)
  const catRows = arr(cats?.rows ?? cats?.items ?? cats?.list ?? cats?.candidates)

  return (
    <section id="screens" className="scroll-mt-24 pt-10 border-t border-hairline mt-10">
      <h2 className="text-lg font-semibold text-ink pb-4">
        Screens <span className="text-accent">·</span>{' '}
        <span className="text-sm font-normal text-muted">
          deterministic scanners over the universe
        </span>
      </h2>

      {changes && (
        <div className="flex flex-wrap gap-2 pb-4">
          {arr(changes.new).map((r, i) => (
            <Chip key={`n${i}`} label={`NEW ${fmtShort((r as Record<string, unknown>)?.symbol ?? r)}`} tone="ok" />
          ))}
          {arr(changes.improving).slice(0, 5).map((r, i) => (
            <Chip key={`u${i}`} label={`↑ ${fmtShort(r).slice(0, 24)}`} tone="ok" />
          ))}
          {arr(changes.falling).slice(0, 5).map((r, i) => (
            <Chip key={`d${i}`} label={`↓ ${fmtShort(r).slice(0, 24)}`} tone="warn" />
          ))}
          {arr(changes.removed).slice(0, 5).map((r, i) => (
            <Chip key={`r${i}`} label={`out ${fmtShort(r).slice(0, 24)}`} tone="off" />
          ))}
        </div>
      )}

      {gemRows.length > 0 && (
        <Section title="Hidden gems" subtitle="emerging growth · 0–125" defaultOpen>
          <ScreenTable
            rows={gemRows}
            cols={[['symbol', ''], ['final', 'score'], ['growth', 'growth'],
            ['tape', 'tape'], ['momentum_state', 'mom'], ['fwd_pe', 'fwd pe']]}
          />
        </Section>
      )}
      {catRows.length > 0 && (
        <Section title="Tailwind candidates" subtitle="early CAT · repricing not done" defaultOpen>
          <ScreenTable
            rows={catRows}
            cols={[['symbol', ''], ['score', 'score'], ['rev_accel', 'rev accel'],
            ['revision', 'revisions'], ['fv_upside', 'fv gap'], ['momentum_state', 'mom']]}
          />
        </Section>
      )}
      {gemRows.length === 0 && catRows.length === 0 && (
        <p className="text-sm text-muted">No screen output today.</p>
      )}
    </section>
  )
}

/* ---------------- expressions ---------------- */

function ExpressionsSection({ sheet }: { sheet: Record<string, unknown> | null }) {
  const rows = arr(sheet?.rows ?? sheet?.items ?? sheet?.list ?? sheet)
  return (
    <section id="expressions" className="scroll-mt-24 pt-10 border-t border-hairline mt-10">
      <h2 className="text-lg font-semibold text-ink pb-4">
        Expressions <span className="text-accent">·</span>{' '}
        <span className="text-sm font-normal text-muted">
          how the conviction becomes a position
        </span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">
          No daily sheet rows — conviction names translate to stock zones
          and LEAP expressions after the nightly sheet runs.
        </p>
      ) : (
        <div className="divide-y divide-hairline/60 rounded-xl border border-hairline bg-card px-5 py-2">
          {rows.slice(0, 20).map((r, i) => (
            <div key={i} className="py-3 flex items-start justify-between gap-3 text-sm">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <Sym s={r.symbol} />
                  {r.lane != null && (
                    <span className="rounded-full bg-elevated px-2 py-0.5 text-[10px] text-muted">
                      {String(r.lane)}
                    </span>
                  )}
                </div>
                <div className="pt-1 text-xs text-muted">
                  {fmtShort(r).slice(0, 160)}
                </div>
              </div>
              {r.zone != null && (
                <span className="shrink-0 font-mono text-xs text-accent">
                  {fmtShort(r.zone).slice(0, 40)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default async function DeskPage() {
  const [strategy, conviction, gems, cats, sheet] = await Promise.all([
    api.strategy(),
    api.conviction(),
    api.hiddenGems(),
    api.tailwindCandidates(),
    api.dailySheet(),
  ])

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-2">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          The desk · <span className="text-accent">elite</span>
        </div>
        <h1 className="pt-3 font-semibold text-display text-ink">
          Planning <span className="text-accent">→</span> conviction{' '}
          <span className="text-accent">→</span> expression
        </h1>
      </header>

      <SubNav />
      <Gate feature="detail_sections">
        <PlannerSection s={strategy} />
        <ConvictionSection c={conviction} />
        <ScreensSection gems={gems} cats={cats} />
        <ExpressionsSection sheet={sheet} />
      </Gate>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — strategy journaled daily; the desk plans, you decide</span>
        <span className="font-mono">
          {strategy?.as_of ? String(strategy.as_of).slice(0, 16) : ''}
        </span>
      </footer>
    </main>
  )
}
