import type { IntradayTape } from '@/lib/api'
import { TAPE_LABEL, TAPE_TONE } from '@/components/tape-chips'
import { RefreshButton } from '@/components/refresh-button'

type Tl = NonNullable<IntradayTape['timeline']>[number]

const ET = 'America/New_York'

function hhmm(ts: string) {
  // journaled ts is already ET-annotated (…-04:00); fall back to a
  // plain slice when it isn't ISO
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts.slice(11, 16) || ts
  return d.toLocaleTimeString('en-US', {
    timeZone: ET, hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function readingsLine(t: Tl) {
  const bits: string[] = []
  if (t.qqq_chg_open != null)
    bits.push(`QQQ ${t.qqq_chg_open >= 0 ? '+' : ''}${(t.qqq_chg_open * 100).toFixed(1)}% vs open`)
  if (t.above_vwap != null)
    bits.push(t.above_vwap ? (t.vwap_held ? 'above+held VWAP' : 'above VWAP') : 'below VWAP')
  if (t.vix != null)
    bits.push(`VIX ${t.vix}${t.vix_rising ? '↑' : t.vix_falling ? '↓' : ''}`)
  if (t.breadth_adv_pct != null)
    bits.push(`${t.breadth_adv_pct}% green vs open`)
  if (t.leadership && t.leadership !== 'broad')
    bits.push(t.leadership === 'ai_led' ? 'AI-led' : 'defensive-led')
  if (t.macro_pressure)
    bits.push('rates+oil pressing')
  return bits.join(' · ')
}

/** Session tape — the day as a sequence of journaled tape states with
    the readings that produced each transition: the "it gapped, rallied,
    faded — why" answer, refreshed every eval (15 min during RTH). */
export function SessionTape({ tape }: { tape: IntradayTape | null }) {
  // dedupe repeated timestamps — the job and the lazy-eval can both
  // write the same eval when they overlap
  const tl = (tape?.timeline ?? []).filter(
    (t, i, a) => i === 0 || t.ts !== a[i - 1].ts,
  )
  if (tl.length < 2) return null

  // collapse consecutive same-state evals into segments — each row is
  // a transition, carrying the evidence at the moment the tape flipped
  const segments: { start: Tl; rows: Tl[] }[] = []
  for (const t of tl) {
    const last = segments[segments.length - 1]
    if (last && last.start.state === t.state) last.rows.push(t)
    else segments.push({ start: t, rows: [t] })
  }
  const lastT = tl[tl.length - 1]

  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4 mb-2">
      <div className="flex items-baseline justify-between">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Session tape
        </div>
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-[11px] text-faint">
            {tl.length} evals · last {hhmm(lastT.ts)} ET
          </span>
          <RefreshButton />
        </span>
      </div>

      <div className="pt-4 space-y-2.5">
        {segments.map((seg, i) => {
          const t = seg.start
          const live = i === segments.length - 1
          const lastRow = seg.rows[seg.rows.length - 1]
          // coverage is legible: a segment isn't one record — it's N
          // evals that held the same state, and the span proves it
          const span = seg.rows.length > 1
            ? live
              ? `running since ${hhmm(t.ts)} · ${seg.rows.length} evals ▾`
              : `ran ${hhmm(t.ts)}–${hhmm(lastRow.ts)} · ${seg.rows.length} evals ▾`
            : null
          const head = (
            <>
              <span
                className={`text-[13px] font-medium ${TAPE_TONE[t.state] ?? 'text-muted'}`}
              >
                {TAPE_LABEL[t.state] ?? t.state.replace(/_/g, ' ')}
              </span>
              {live && (
                <span className="ml-2 text-[10px] uppercase tracking-wider text-faint">
                  now
                </span>
              )}
              {span && (
                <span className="ml-2 text-[11px] text-faint">{span}</span>
              )}
              <div className="mt-0.5 font-mono text-[11px] leading-relaxed text-muted">
                {readingsLine(t)}
              </div>
            </>
          )
          return (
            <div key={`${t.ts}-${i}`} className="flex gap-3 items-baseline">
              <span className="w-11 shrink-0 font-mono text-[11px] text-faint">
                {hhmm(t.ts)}
              </span>
              {seg.rows.length > 1 ? (
                <details className="min-w-0 group">
                  <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                    {head}
                  </summary>
                  <div className="mt-1.5 space-y-1 border-l border-hairline pl-3">
                    {seg.rows.map((r) => (
                      <div
                        key={r.ts}
                        className="flex gap-2 items-baseline font-mono text-[11px]"
                      >
                        <span className="w-11 shrink-0 text-faint">
                          {hhmm(r.ts)}
                        </span>
                        <span className="text-muted">
                          {readingsLine(r) || r.state.replace(/_/g, ' ')}
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              ) : (
                <div className="min-w-0">{head}</div>
              )}
            </div>
          )
        })}
      </div>

      {tape?.eval?.evidence && tape.eval.evidence.length > 0 && (
        <div className="pt-3 mt-3 border-t border-hairline/60 space-y-0.5">
          {tape.eval.evidence.slice(0, 6).map((e, i) => (
            <p key={i} className="text-[11px] leading-relaxed text-muted">
              · {e}
            </p>
          ))}
        </div>
      )}
    </section>
  )
}
