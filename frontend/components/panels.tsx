/** Decision-grade panels for the stock page — pure/server-safe.
 * Meters, direction arrows, balance bars, level ladders. Green good,
 * red bad, yellow caution — site signal language. */

function n(v: unknown): number | null {
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

function pctStr(v: unknown, dec = 1, sign = true): string {
  const x = n(v)
  if (x === null) return '—'
  const p = x * 100
  return `${sign && p >= 0 ? '+' : ''}${p.toFixed(dec)}%`
}

function ptsStr(v: unknown, dec = 0): string {
  const x = n(v)
  if (x === null) return '—'
  const p = x * 100
  return `${p >= 0 ? '+' : ''}${p.toFixed(dec)}pts`
}

function dirTone(x: number | null, invert = false): string {
  if (x === null || x === 0) return 'text-muted'
  const good = invert ? x < 0 : x > 0
  return good ? 'text-aggressive' : 'text-defensive'
}

function Arrow({ v, invert = false }: { v: number | null; invert?: boolean }) {
  if (v === null || Math.abs(v) < 0.0001)
    return <span className="text-faint">→</span>
  const good = invert ? v < 0 : v > 0
  return (
    <span className={good ? 'text-aggressive' : 'text-defensive'}>
      {v > 0 ? '▲' : '▼'}
    </span>
  )
}

/** Horizontal meter — a marker on a scale with optional good/warn zones. */
function Meter({
  v, lo, hi, zones,
}: {
  v: number | null
  lo: number
  hi: number
  zones?: [number, number, string][]   // [from,to,cssColor] left→right
}) {
  const frac = v === null ? 0 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)))
  return (
    <span className="relative inline-block h-[6px] w-24 rounded-full bg-hairline align-middle">
      {(zones ?? []).map(([a, b, c], i) => (
        <span
          key={i}
          className={`absolute inset-y-0 rounded-full ${c}`}
          style={{
            left: `${Math.max(0, (a - lo) / (hi - lo)) * 100}%`,
            width: `${(Math.min(hi, b) - Math.max(lo, a)) / (hi - lo) * 100}%`,
          }}
        />
      ))}
      {v !== null && (
        <span
          className="absolute -top-[3px] h-3 w-[3px] rounded-full bg-ink"
          style={{ left: `calc(${frac * 100}% - 1.5px)` }}
        />
      )}
    </span>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3px] text-[13px]">
      <span className="text-muted">{label}</span>
      <span className="flex items-baseline gap-2 text-right">{children}</span>
    </div>
  )
}

function Chip({ v, map }: { v: unknown; map?: Record<string, string> }) {
  const s = String(v ?? '—').toLowerCase().replace(/_/g, ' ')
  const cls =
    map?.[String(v ?? '').toLowerCase()] ??
    (['broken', 'still_falling', 'capitulation', 'bearish', 'no', 'deteriorating', 'slowing']
      .some((t) => s.includes(t)) ? 'border-defensive/40 text-defensive'
      : ['confirmed', 'accelerating', 'improving', 'strong', 'healthy', 'basing', 'up']
        .some((t) => s.includes(t)) ? 'border-aggressive/40 text-aggressive'
        : 'border-caution/40 text-caution')
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider ${cls}`}>
      {s}
    </span>
  )
}

export function StateChip({ v }: { v: unknown }) {
  return <Chip v={v} />
}

/* ────────────────────────────── fundamentals ────────────────────────────── */

export function FundPanel({ d }: { d: Record<string, unknown> }) {
  const cur = (d.cur && typeof d.cur === 'object' ? d.cur : {}) as Record<string, unknown>
  const rev = (d.revision && typeof d.revision === 'object' ? d.revision : {}) as Record<string, unknown>
  const pos = Array.isArray(d.pos) ? (d.pos as unknown[]) : []
  const neg = Array.isArray(d.neg) ? (d.neg as unknown[]) : []
  const total = pos.length + neg.length

  return (
    <div>
      {/* verdict line */}
      <div className="flex flex-wrap items-center gap-2">
        <Chip v={d.state} />
        {rev.grade != null && (
          <span className="rounded-full border border-aggressive/40 px-2 py-0.5 text-[10.5px] font-semibold text-aggressive">
            est-revision {String(rev.grade)}{rev.score != null && ` · ${rev.score}`}
          </span>
        )}
        {d.demand_health != null && <Chip v={`demand ${d.demand_health}`} />}
      </div>

      {/* growth */}
      <div className="pt-3">
        <div className="text-[10px] uppercase tracking-wider text-faint">growth</div>
        <Row label="revenue">
          <Arrow v={n(cur.rev_growth)} />
          <span className={`font-mono ${dirTone(n(cur.rev_growth))}`}>
            {pctStr(cur.rev_growth, 0)}
          </span>
        </Row>
        <Row label="eps">
          <Arrow v={n(cur.eps_growth)} />
          <span className={`font-mono ${dirTone(n(cur.eps_growth))}`}>
            {pctStr(cur.eps_growth, 0)}
          </span>
        </Row>
      </div>

      {/* acceleration — is growth speeding up or fading */}
      <div className="pt-2">
        <div className="text-[10px] uppercase tracking-wider text-faint">
          acceleration <span className="normal-case">(is growth fading?)</span>
        </div>
        <Row label="rev accel">
          <Arrow v={n(cur.rev_accel)} />
          <span className={`font-mono ${dirTone(n(cur.rev_accel))}`}>
            {ptsStr(cur.rev_accel)}
          </span>
        </Row>
        <Row label="eps accel">
          <Arrow v={n(cur.eps_accel)} />
          <span className={`font-mono ${dirTone(n(cur.eps_accel))}`}>
            {ptsStr(cur.eps_accel)}
          </span>
        </Row>
        <Row label="gross margin">
          <Arrow v={n(cur.gm_qoq)} />
          <span className={`font-mono ${dirTone(n(cur.gm_qoq))}`}>
            {pctStr(cur.gm_now, 0, false)}{' '}
            <span className="text-faint">{ptsStr(cur.gm_qoq, 1)} qoq</span>
          </span>
        </Row>
      </div>

      {/* quality tape */}
      <div className="pt-2">
        <div className="text-[10px] uppercase tracking-wider text-faint">quality tape</div>
        <Row label="beat streak">
          <span className={`font-mono ${n(cur.beat_streak) !== null && n(cur.beat_streak)! >= 3 ? 'text-aggressive' : 'text-muted'}`}>
            {cur.beat_streak != null ? `${String(cur.beat_streak)}q` : '—'}
          </span>
        </Row>
        <Row label="surprise trend">
          <Arrow v={n(cur.surprise_trend)} />
          <span className={`font-mono ${dirTone(n(cur.surprise_trend))}`}>
            {n(cur.surprise_trend) !== null ? `${n(cur.surprise_trend)! >= 0 ? '+' : ''}${n(cur.surprise_trend)!.toFixed(0)}pts` : '—'}
          </span>
        </Row>
        <Row label="est revisions 30d">
          <Arrow v={n(cur.est_revision_pct ?? rev.er)} />
          <span className={`font-mono ${dirTone(n(cur.est_revision_pct ?? rev.er))}`}>
            {pctStr(cur.est_revision_pct ?? rev.er, 0)}
          </span>
        </Row>
      </div>

      {/* evidence balance */}
      {total > 0 && (
        <div className="pt-3">
          <div className="flex h-[7px] overflow-hidden rounded-full">
            <div className="bg-aggressive" style={{ width: `${(pos.length / total) * 100}%` }} />
            <div className="bg-defensive" style={{ width: `${(neg.length / total) * 100}%` }} />
          </div>
          <div className="flex justify-between pt-1 font-mono text-[11px]">
            <span className="text-aggressive">{pos.length} working for</span>
            <span className="text-defensive">{neg.length} against</span>
          </div>
          {neg.length > 0 && (
            <div className="pt-1.5 space-y-0.5">
              {neg.map((x, i) => (
                <div key={i} className="text-[12px] text-defensive">▼ {String(x)}</div>
              ))}
            </div>
          )}
          {pos.length > 0 && (
            <div className="pt-1 space-y-0.5">
              {pos.map((x, i) => (
                <div key={i} className="text-[12px] text-aggressive">▲ {String(x)}</div>
              ))}
            </div>
          )}
        </div>
      )}
      {d.decel_cause != null && (
        <p className="pt-2 text-[11px] text-faint">
          cause: {String(d.decel_cause).replace(/_/g, ' ')}
        </p>
      )}
    </div>
  )
}

/* ──────────────────────────────── tape ──────────────────────────────────── */

export function TapePanel({ d, spot }: { d: Record<string, unknown>; spot?: number }) {
  const swing = (d.swing && typeof d.swing === 'object' ? d.swing : {}) as Record<string, unknown>
  const rsi = n(d.rsi)
  const pb = n(d.pct_b)

  // level ladder — every known level + spot on one ruler
  const levels = [
    { k: 'swing low', v: n(swing.swing_low) },
    { k: 'prior low', v: n(swing.prior_low) },
    { k: 'avwap', v: n(swing.avwap) },
    { k: 'support', v: n(swing.support_px) },
    { k: 'confirm', v: n(swing.confirm_level) },
  ].filter((x): x is { k: string; v: number } => x.v !== null)
  const px = n(spot)
  const ladderLo = Math.min(...levels.map((x) => x.v), px ?? Infinity)
  const ladderHi = Math.max(...levels.map((x) => x.v), px ?? -Infinity)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip v={d.state} />
        {d.dip_phase != null && <Chip v={`dip ${d.dip_phase}`} />}
        {swing.phase != null && <Chip v={`swing ${swing.phase}`} />}
      </div>

      {/* oscillator meters */}
      <div className="pt-3">
        <Row label="RSI">
          <Meter v={rsi} lo={0} hi={100}
            zones={[[0, 30, 'bg-caution/30'], [30, 70, 'bg-hairline'], [70, 100, 'bg-caution/30']]} />
          <Arrow v={n(d.rsi_dir)} />
          <span className={`font-mono ${rsi !== null && rsi < 30 ? 'text-caution' : rsi !== null && rsi > 70 ? 'text-caution' : 'text-muted'}`}>
            {rsi?.toFixed(0) ?? '—'}
          </span>
        </Row>
        <Row label="%B (bollinger)">
          <Meter v={pb} lo={-0.5} hi={1.5}
            zones={[[-0.5, 0, 'bg-defensive/30'], [0, 1, 'bg-hairline'], [1, 1.5, 'bg-caution/30']]} />
          <span className={`font-mono ${pb !== null && pb < 0 ? 'text-defensive' : 'text-muted'}`}>
            {pb?.toFixed(2) ?? '—'}
          </span>
        </Row>
        <Row label="MACD hist">
          <Arrow v={n(d.hist_dir)} />
          <span className={`font-mono ${dirTone(n(d.hist))}`}>
            {n(d.hist)?.toFixed(1) ?? '—'}
          </span>
        </Row>
      </div>

      {/* trend distances */}
      <div className="pt-2">
        <div className="text-[10px] uppercase tracking-wider text-faint">trend</div>
        <Row label="3m return">
          <Arrow v={n(d.ret_3m)} />
          <span className={`font-mono ${dirTone(n(d.ret_3m))}`}>
            {pctStr(d.ret_3m)}
          </span>
        </Row>
        <Row label="vs 50dma">
          <Arrow v={n(d.vs_sma50)} />
          <span className={`font-mono ${dirTone(n(d.vs_sma50))}`}>
            {pctStr(d.vs_sma50)}
          </span>
        </Row>
        <Row label="vs 200dma">
          <Arrow v={n(d.vs_sma200)} />
          <span className={`font-mono ${dirTone(n(d.vs_sma200))}`}>
            {pctStr(d.vs_sma200)}
          </span>
        </Row>
        <Row label="drawdown from 52w high">
          <span className={`font-mono ${n(d.dd52w) !== null && n(d.dd52w)! < -0.2 ? 'text-defensive' : 'text-muted'}`}>
            {pctStr(d.dd52w, 0, false)}
          </span>
        </Row>
      </div>

      {/* level ladder */}
      {levels.length > 1 && ladderHi > ladderLo && (
        <div className="pt-3">
          <div className="text-[10px] uppercase tracking-wider text-faint">
            levels — where price sits
          </div>
          <div className="relative mt-3 h-1.5 rounded-full bg-hairline">
            {levels.map((x) => (
              <span key={x.k}
                className="absolute -top-1 h-3.5 w-[2px] bg-faint"
                style={{ left: `${((x.v - ladderLo) / (ladderHi - ladderLo)) * 100}%` }}
                title={`${x.k} ${x.v}`} />
            ))}
            {px !== null && (
              <span
                className="absolute -top-[7px] h-5 w-[3px] rounded-full bg-accent"
                style={{ left: `${((px - ladderLo) / (ladderHi - ladderLo)) * 100}%` }} />
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10.5px] text-muted">
            {[...levels].sort((a, b) => a.v - b.v).map((x) => (
              <span key={x.k}>
                <span className="text-faint">{x.k}</span> {x.v >= 1000 ? x.v.toFixed(0) : x.v.toFixed(2)}
              </span>
            ))}
            {px !== null && (
              <span className="text-accent">spot {px >= 1000 ? px.toFixed(0) : px.toFixed(2)}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
