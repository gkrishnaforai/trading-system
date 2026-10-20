import Link from 'next/link'
import { api, type BoardItem } from '@/lib/api'
import { Chip, Gate, Stat } from '@/components/regime'
import { VolChips } from '@/components/vol-chips'

const ACTION_TONE: Record<string, string> = {
  EXIT: 'border-defensive/40 text-defensive',
  TRIM: 'border-caution/40 text-caution',
  PUT: 'border-defensive/40 text-defensive',
  BOUNCE: 'border-aggressive/40 text-aggressive',
  ACCUMULATE: 'border-aggressive/40 text-aggressive',
}

const ENTRY_TONE: Record<string, 'ok' | 'warn' | 'off'> = {
  ready: 'ok',
  watch_zone: 'warn',
  frozen: 'off',
  peer_drag: 'warn',
}

function fmtMoney(v?: number) {
  if (v == null) return null
  return `$${Math.round(v).toLocaleString('en-US')}`
}

function fmtPct(v?: number) {
  if (v == null) return null
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function BoardRow({ it }: { it: BoardItem }) {
  const action = String(it.action ?? '—')
  const tone =
    ACTION_TONE[action] ?? 'border-hairline text-muted'
  const status = it.entry_status ? String(it.entry_status) : null
  return (
    <div className="py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-[10px] font-semibold tracking-wider ${tone}`}
          >
            {action}
          </span>
          <Link
            href={`/stock?sym=${encodeURIComponent(String(it.symbol ?? ''))}`}
            className="font-semibold text-ink hover:text-accent transition-colors"
          >
            {String(it.symbol ?? '—')}
          </Link>
          {it.in_portfolio && (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
              held
            </span>
          )}
          {status && (
            <Chip label={status} tone={ENTRY_TONE[status] ?? 'warn'} />
          )}
        </div>
        <div className="flex items-baseline gap-4 shrink-0 font-mono text-xs text-muted">
          {it.price != null && <span>${Number(it.price).toFixed(2)}</span>}
          {it.gain_pct != null && (
            <span
              className={
                Number(it.gain_pct) >= 0 ? 'text-aggressive' : 'text-defensive'
              }
            >
              {fmtPct(Number(it.gain_pct))}
            </span>
          )}
          {it.days_to_earnings != null && Number(it.days_to_earnings) <= 14 && (
            <span className="text-caution">
              ⚠ EPS {String(it.days_to_earnings)}d
            </span>
          )}
          <span className="text-ink">
            {it.score != null ? `${it.score}` : ''}
          </span>
        </div>
      </div>
      <div className="pt-1 pl-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted">
        {it.instrument && <span>{String(it.instrument)}</span>}
        {it.momentum && <span>mom {String(it.momentum)}</span>}
        {it.entry != null && <span>entry ${Number(it.entry).toFixed(2)}</span>}
        {it.stop != null && (
          <span className="text-defensive">stop ${Number(it.stop).toFixed(2)}</span>
        )}
        {it.target != null && (
          <span className="text-aggressive">
            tgt ${Number(it.target).toFixed(2)}
          </span>
        )}
      </div>
      {Array.isArray(it.why) && it.why.length > 0 && (
        <ul className="pt-1.5 pl-1 space-y-0.5 text-xs text-muted leading-relaxed">
          {it.why.slice(0, 4).map((w, i) => (
            <li key={i}>· {String(w)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

const TAPE_TONE: Record<string, string> = {
  buyers_in_control: 'text-aggressive',
  sellers_regaining: 'text-defensive',
  narrow_fragile: 'text-caution',
  sellers_exhausting: 'text-accent',
  chop_unconfirmed: 'text-faint',
}
const TAPE_LABEL: Record<string, string> = {
  buyers_in_control: 'buyers in control',
  sellers_regaining: 'sellers regaining',
  narrow_fragile: 'narrow, fragile bounce',
  sellers_exhausting: 'sellers exhausting',
  chop_unconfirmed: 'chop — unconfirmed',
}

export default async function BoardPage() {
  const [board, posture, tape] = await Promise.all([
    api.daily(), api.posture(), api.intraday(),
  ])
  const items = board?.items ?? []
  const counts = board?.counts ?? {}
  const stance = board?.posture?.stance ?? '—'
  const stanceTone =
    String(stance).startsWith('GREED') ? 'text-aggressive'
      : String(stance).startsWith('FEAR') ? 'text-defensive'
        : String(stance).startsWith('DEFENSIVE') ? 'text-defensive'
          : 'text-neutral'

  return (
    <main className="mx-auto max-w-3xl px-5 pb-20">
      <header className="pt-6 pb-8">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Daily board
        </div>
        <h1 className="pt-3 font-semibold text-display">
          <span className={stanceTone}>{String(stance)}</span>
        </h1>
        {board?.posture?.note && (
          <p className="pt-4 max-w-xl text-[15px] leading-relaxed text-muted">
            {board.posture.note}
          </p>
        )}
        <div className="pt-4">
          <VolChips vol={posture?.vol} bias={posture?.bias} />
        </div>
        {tape?.state && tape.state !== 'no_evals_today' && tape.eval && (
          <div className="pt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
            <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
              tape
            </span>
            <span className={`font-medium ${TAPE_TONE[tape.state] ?? 'text-muted'}`}>
              {TAPE_LABEL[tape.state] ?? tape.state}
            </span>
            {tape.eval.qqq_chg_open != null && (
              <span className="font-mono text-muted">
                QQQ {(tape.eval.qqq_chg_open * 100).toFixed(1)}%
              </span>
            )}
            {tape.eval.above_vwap != null && (
              <span className={`font-mono ${tape.eval.above_vwap ? 'text-aggressive' : 'text-defensive'}`}>
                {tape.eval.above_vwap ? '>VWAP' : '<VWAP'}
                {tape.eval.vwap_held ? ' held' : ''}
              </span>
            )}
            {tape.eval.breadth_adv_pct != null && (
              <span className="font-mono text-muted">
                {tape.eval.breadth_adv_pct}% adv
              </span>
            )}
            {tape.eval.vix != null && (
              <span className="font-mono text-muted">
                VIX {tape.eval.vix}
                {tape.eval.vix_falling ? '↓' : tape.eval.vix_rising ? '↑' : ''}
              </span>
            )}
            {tape.eval.morning_recovery && (
              <span className="text-muted">am↓→green</span>
            )}
            {tape.eval.macro_pressure && (
              <span className="text-caution">⚠macro</span>
            )}
            {(tape.timeline ?? []).length > 2 && (
              <span className="text-faint" title={
                (tape.timeline ?? []).map((t) => `${t.ts.slice(11, 16)} ${t.state}`).join(' · ')
              }>
                {tape.timeline!.length} evals
              </span>
            )}
          </div>
        )}
      </header>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-6 rounded-xl border border-hairline bg-card px-5 py-4">
        <Stat
          label="Exits / Trims"
          value={String(counts.exits ?? 0)}
        />
        <Stat
          label="Puts"
          value={String(counts.puts ?? 0)}
        />
        <Stat
          label="Accumulate"
          value={String(counts.accumulate ?? 0)}
        />
        <Stat
          label="Tranche"
          value={fmtMoney(board?.suggested_tranche) ?? '—'}
        />
      </section>

      <div className="mt-8 border-t border-hairline">
        <Gate feature="board">
          {items.length === 0 ? (
            <p className="py-8 text-sm text-muted">
              No board actions today — the board only surfaces when the
              evidence meets the bar. No trade is a valid outcome.
            </p>
          ) : (
            <div className="divide-y divide-hairline/60">
              {items.map((it, i) => (
                <BoardRow key={`${it.symbol}-${i}`} it={it} />
              ))}
            </div>
          )}
        </Gate>
      </div>

      <footer className="mt-16 border-t border-hairline pt-6 flex justify-between text-[11px] text-faint">
        <span>advisory — exits first, then deploys; human decides</span>
        <span className="font-mono">
          {board?.as_of ? String(board.as_of).slice(0, 19) : ''}
        </span>
      </footer>
    </main>
  )
}
