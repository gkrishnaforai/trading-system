import type { IntradayTape } from '@/lib/api'

export const TAPE_TONE: Record<string, string> = {
  buyers_in_control: 'text-aggressive',
  sellers_regaining: 'text-defensive',
  narrow_fragile: 'text-caution',
  sellers_exhausting: 'text-accent',
  chop_unconfirmed: 'text-faint',
}
export const TAPE_LABEL: Record<string, string> = {
  buyers_in_control: 'buyers in control',
  sellers_regaining: 'sellers regaining',
  narrow_fragile: 'narrow, fragile bounce',
  sellers_exhausting: 'sellers exhausting',
  chop_unconfirmed: 'chop — unconfirmed',
}

export function TapeChips({ tape }: { tape: IntradayTape | null }) {
  if (!tape?.state || tape.state === 'no_evals_today' || !tape.eval) {
    return null
  }
  const e = tape.eval
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">
      <span className="text-[10px] uppercase tracking-[0.18em] text-faint">
        tape
      </span>
      <span className={`font-medium ${TAPE_TONE[tape.state] ?? 'text-muted'}`}>
        {TAPE_LABEL[tape.state] ?? tape.state}
      </span>
      {e.qqq_chg_open != null && (
        <span className="font-mono text-muted">
          QQQ {(e.qqq_chg_open * 100).toFixed(1)}%
        </span>
      )}
      {e.above_vwap != null && (
        <span className={`font-mono ${e.above_vwap ? 'text-aggressive' : 'text-defensive'}`}>
          {e.above_vwap ? '>VWAP' : '<VWAP'}
          {e.vwap_held ? ' held' : ''}
        </span>
      )}
      {e.breadth_adv_pct != null && (
        <span className="font-mono text-muted">
          {e.breadth_adv_pct}% adv
        </span>
      )}
      {e.vix != null && (
        <span className="font-mono text-muted">
          VIX {e.vix}
          {e.vix_falling ? '↓' : e.vix_rising ? '↑' : ''}
        </span>
      )}
      {e.morning_recovery && (
        <span className="text-muted">am↓→green</span>
      )}
      {e.macro_pressure && (
        <span className="text-caution">⚠macro</span>
      )}
      {(tape.timeline ?? []).length > 2 && (
        <span
          className="text-faint"
          title={(tape.timeline ?? [])
            .map((t) => `${t.ts.slice(11, 16)} ${t.state}`)
            .join(' · ')}
        >
          {tape.timeline!.length} evals
        </span>
      )}
    </div>
  )
}
