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
  if (t.smh_above_vwap != null)
    bits.push(
      t.smh_above_vwap
        ? `SMH ${t.smh_vwap_held ? 'above+held' : 'above'} VWAP`
        : 'SMH below VWAP',
    )
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
  const br = tape?.base_rate
  const obr = tape?.open_base_rate
  const slots = tape?.premarket?.slots ?? []
  const pmF = slots.find((s) => s.slot === 'final')
  const pmE = slots.find((s) => s.slot === 'early')
  const pm = pmF ?? pmE
  const pmDrift =
    pmF?.qqq_gap != null && pmE?.qqq_gap != null
      ? pmF.qqq_gap - pmE.qqq_gap
      : null

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

      {pm && (
        <div className="pt-1.5 font-mono text-[11px] text-faint"
          title="journaled pre-market snapshot — extended-hours gap vs prior close, crypto 24h; early→final drift shows the gap firming or fading into the open">
          premarket{pmF ? '' : ' (early)'}:{' '}
          {[
            pm.qqq_gap != null && `QQQ ${pm.qqq_gap >= 0 ? '+' : ''}${(pm.qqq_gap * 100).toFixed(1)}%`,
            pm.smh_gap != null && `SMH ${pm.smh_gap >= 0 ? '+' : ''}${(pm.smh_gap * 100).toFixed(1)}%`,
            pm.btc_chg != null && `BTC ${pm.btc_chg >= 0 ? '+' : ''}${(pm.btc_chg * 100).toFixed(1)}%/24h`,
          ].filter(Boolean).join(' · ') || 'no legs read'}
          {pmDrift != null && Math.abs(pmDrift) > 0.0005 &&
            ` — gap ${pmDrift > 0 ? 'firmed' : 'faded'} ${pmDrift >= 0 ? '+' : ''}${(pmDrift * 100).toFixed(1)}pp into open`}
        </div>
      )}

      {tape?.eval?.levels && Object.keys(tape.eval.levels).length > 0 && (
        <div className="pt-1.5 space-y-0.5 font-mono text-[11px]">
          <div className="text-faint"
            title="session VWAP scoreboard + tomorrow's checklist — reclaim = vwap to retake, confirm = opening-range high, support = last-hour low, warning = session low. A checklist, not a signal.">
            levels
          </div>
          {(['SMH', 'QQQ', 'SPY', 'IWM'] as const).map((sym) => {
            const lv = tape.eval!.levels![sym]
            if (!lv?.vwap) return null
            return (
              <div key={sym} className="text-faint">
                <span className={lv.above ? 'text-aggressive' : 'text-defensive'}>
                  {sym} {lv.dist_pct != null && `${lv.dist_pct >= 0 ? '+' : ''}${lv.dist_pct.toFixed(1)}%`} vs vwap
                </span>
                {' · reclaim '}{lv.reclaim}
                {' · confirm '}{lv.confirm}
                {' · support '}{lv.support}
                {' · break <'}{lv.warning}
              </div>
            )
          })}
        </div>
      )}

      {lastT.smh_above_vwap != null && (
        <div className="pt-1.5 font-mono text-[11px] text-faint">
          sector:{' '}
          {lastT.smh_above_vwap
            ? lastT.smh_vwap_held
              ? 'SMH reclaiming VWAP — rebound attempt'
              : 'SMH above VWAP, unconfirmed'
            : 'SMH below VWAP — sector still pressured'}
        </div>
      )}

      {br && br.n != null && (
        <div className="pt-1 font-mono text-[11px] text-faint"
          title="base rates from journaled sessions — context, not a forecast">
          history: {br.n} sessions ending{' '}
          {(br.state ?? '').replace(/_/g, ' ')} →{' '}
          {br.day_median != null &&
            `close med ${br.day_median >= 0 ? '+' : ''}${(br.day_median * 100).toFixed(1)}%`}
          {br.day_red_pct != null &&
            `, ${Math.round(br.day_red_pct * 100)}% red`}
          {br.next_median != null &&
            ` · next day med ${br.next_median >= 0 ? '+' : ''}${(br.next_median * 100).toFixed(1)}%`}
        </div>
      )}

      {obr && obr.n != null && (
        <div className="pt-1 font-mono text-[11px] text-faint"
          title="sessions that opened with this tape signature (first-3-evals mode) → same-day close — the journal's own measure of how early the tape becomes informative">
          opened like this: {obr.n} sessions starting{' '}
          {(obr.state ?? '').replace(/_/g, ' ')} →{' '}
          {obr.day_median != null &&
            `close med ${obr.day_median >= 0 ? '+' : ''}${(obr.day_median * 100).toFixed(1)}%`}
          {obr.day_red_pct != null &&
            `, ${Math.round(obr.day_red_pct * 100)}% red`}
        </div>
      )}

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
