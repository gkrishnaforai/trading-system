// the call — deterministic composite lean from the health card's own
// fields (rsi zone, %B, macd-hist direction, avwap relation, dip phase,
// swing structure, at-support proximity). No new numbers invented —
// the score just re-weights what the card already computed.
type Dict = Record<string, unknown>

const num = (v: unknown) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const money = (v: unknown) => {
  const n = num(v)
  return n == null ? '—' : `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}
const obj = (v: unknown): Dict | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Dict) : null

export type CallSignals = {
  parts: { txt: string; tone: 'up' | 'dn' | 'mid' }[]
  score: number
  lean: 'up' | 'down' | 'mixed'
  floor: { lo: number | null; hi: number | null }
  reclaim: number | null
  confirm: number | null
  bearConfluence: boolean
  flip: string
  line: string
}

export function callSignals(card: Dict): CallSignals | null {
  const det = obj(obj(card.technical)?.detail) ?? {}
  const sw = obj(det.swing) ?? {}
  const diag = obj(card.diagnosis) ?? {}
  const spot = num(card.spot)
  if (!Object.keys(det).length && !Object.keys(diag).length) return null

  let score = 0
  const parts: CallSignals['parts'] = []
  const push = (txt: string, tone: 'up' | 'dn' | 'mid', pts = 0) => {
    parts.push({ txt, tone })
    score += pts
  }

  const rsi = num(det.rsi)
  if (rsi != null) {
    const r = rsi.toFixed(0)
    if (rsi < 30) push(`RSI ${r} oversold`, 'up', 1)
    else if (rsi < 38) push(`RSI ${r} oversold-lean`, 'up', 0.5)
    else if (rsi > 70) push(`RSI ${r} overbought`, 'dn', -1)
    else if (rsi > 60) push(`RSI ${r} hot`, 'dn', -0.5)
    else push(`RSI ${r}`, 'mid')
  }
  const pb = num(det.pct_b)
  if (pb != null) {
    const b = pb.toFixed(2)
    if (pb < 0) push(`%B ${b} below band`, 'up', 0.5)
    else if (pb > 1.1) push(`%B ${b} extended`, 'dn', -1)
    else if (pb > 0.8) push(`%B ${b} high band`, 'dn', -0.5)
    else push(`%B ${b}`, 'mid')
  }
  const hd = num(det.hist_dir)
  if (hd != null) {
    if (hd > 0.5) push('MACD hist ▲', 'up', 1)
    else if (hd < -0.5) push('MACD hist ▼', 'dn', -1)
    else push('MACD hist →', 'mid')
  }
  const avwap = num(sw.avwap)
  if (avwap != null && spot != null) {
    if (spot >= avwap) push(`above AVWAP ${money(avwap)}`, 'up', 1)
    else push(`below AVWAP ${money(avwap)}`, 'dn', -1)
  }
  const dip = String(det.dip_phase ?? '')
  if (dip) {
    if (/stab|improv|recover|base/i.test(dip)) push(`dip ${dip}`, 'up', 1)
    else if (/fall|knife|new_low/i.test(dip)) push(`dip ${dip}`, 'dn', -1)
    else push(`dip ${dip}`, 'mid')
  }
  const ph = String(sw.phase ?? '')
  if (ph) {
    if (/confirm|uptrend|breakout/i.test(ph) && !/unconfirm/i.test(ph)) {
      push(`swing ${ph}`, 'up', 1)
    } else if (/broken/i.test(ph)) push(`swing ${ph}`, 'dn', -1)
    else if (/unconfirm/i.test(ph)) push(`swing ${ph}`, 'dn', -0.5)
    else push(`swing ${ph}`, 'mid')
  }
  const vs50 = num(det.vs_sma50)
  if (vs50 != null) {
    if (vs50 < 0) push(`${(vs50 * 100).toFixed(1)}% under 50dma`, 'dn', -0.5)
    else push(`+${(vs50 * 100).toFixed(1)}% over 50dma`, 'up', 0.5)
  }
  const dstate = String(diag.state ?? '')
  if (dstate === 'knife') score -= 1
  else if (dstate === 'capitulation') score -= 0.5
  else if (dstate === 'improving' || dstate === 'stabilizing') score += 0.5

  // floor — nearest levels below spot; reclaim/confirm above
  const swingLow = num(sw.swing_low)
  const priorLow = num(sw.prior_low)
  const below = [swingLow, priorLow]
    .filter((v): v is number => v != null && (spot == null || v <= spot * 1.01))
    .sort((a, b) => a - b)
  const floor = { lo: below[0] ?? null, hi: below[below.length - 1] ?? null }
  const nearFloor =
    spot != null && floor.hi != null && (spot - floor.hi) / spot < 0.03
  if (nearFloor) {
    parts.push({ txt: 'testing floor', tone: 'up' })
    score += 0.5
  }
  const confirm = num(sw.confirm_level)
  const reclaim = avwap

  // fv bear ≈ floor = confluence worth naming
  const fv = obj(card.fv)
  const scen = obj(fv?.scenarios)
  const bear = num(scen?.bear)
  const bearConfluence =
    bear != null && floor.lo != null &&
    Math.abs(bear - floor.lo) / bear < 0.03

  const lean = score >= 1.5 ? 'up' : score <= -1.5 ? 'down' : 'mixed'

  const flips: string[] = []
  if (reclaim != null && spot != null && spot < reclaim) {
    flips.push(`reclaims AVWAP ${money(reclaim)}`)
  }
  if (confirm != null && spot != null && spot < confirm) {
    flips.push(`confirms above ${money(confirm)}`)
  }
  if (floor.lo != null) {
    flips.push(`holds the ${money(floor.lo)}${floor.hi && floor.hi !== floor.lo ? `–${money(floor.hi)}` : ''} floor with momentum turning`)
  }

  const line =
    lean === 'down'
      ? `downside favored — oversold readings don't mark a floor while momentum still falls`
      : lean === 'up'
        ? `upside favored — structure and momentum agree`
        : `mixed — waiting on a level to break either way`

  return { parts, score, lean, floor, reclaim, confirm, bearConfluence, flip: flips.join(' · '), line }
}

const toneCls = { up: 'text-aggressive', dn: 'text-defensive', mid: 'text-muted' } as const

export function TheCall({ card }: { card: Dict }) {
  const s = callSignals(card)
  if (!s) return null
  const leanCls =
    s.lean === 'up' ? 'text-aggressive' : s.lean === 'down' ? 'text-defensive' : 'text-caution'
  const leanArrow = s.lean === 'up' ? '▲' : s.lean === 'down' ? '▼' : '◆'

  return (
    <div className="space-y-3">
      {/* line 1 — the tape read, one line of scored facts */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 font-mono text-xs">
        {s.parts.map((p, i) => (
          <span key={i} className={toneCls[p.tone]}>
            {p.txt}
            {i < s.parts.length - 1 && <span className="text-faint"> ·</span>}
          </span>
        ))}
      </div>

      {/* line 2 — the levels that matter */}
      {(s.floor.lo != null || s.reclaim != null || s.confirm != null) && (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
          {s.floor.lo != null && (
            <span className="text-muted">
              floor{' '}
              <span className="font-mono font-semibold text-ink">
                {money(s.floor.lo)}
                {s.floor.hi != null && s.floor.hi !== s.floor.lo && `–${money(s.floor.hi)}`}
              </span>
            </span>
          )}
          {s.reclaim != null && (
            <span className="text-muted">
              reclaim{' '}
              <span className="font-mono font-semibold text-ink">{money(s.reclaim)}</span>
              <span className="text-faint"> avwap</span>
            </span>
          )}
          {s.confirm != null && (
            <span className="text-muted">
              confirm{' '}
              <span className="font-mono font-semibold text-ink">{money(s.confirm)}</span>
            </span>
          )}
          {s.bearConfluence && (
            <span className="text-faint">bear-case FV sits on the floor — confluence</span>
          )}
        </div>
      )}

      {/* line 3 — the lean + what flips it */}
      <div className="border-t border-hairline/60 pt-3">
        <div className={`text-sm font-medium ${leanCls}`}>
          {leanArrow} {s.line}
          <span className="ml-2 font-mono text-[11px] font-normal text-faint">
            score {s.score > 0 ? `+${s.score}` : s.score}
          </span>
        </div>
        {s.flip && (
          <div className="pt-1.5 text-xs text-muted">
            the odds flip when: {s.flip}
          </div>
        )}
      </div>
    </div>
  )
}
