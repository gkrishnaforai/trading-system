export type Tone = 'ok' | 'warn' | 'bad' | 'off'

const DOT: Record<Tone, string> = {
  ok: 'bg-aggressive',
  warn: 'bg-caution',
  bad: 'bg-defensive',
  off: 'bg-faint',
}

const TXT: Record<Tone, string> = {
  ok: 'text-aggressive',
  warn: 'text-caution',
  bad: 'text-defensive',
  off: 'text-muted',
}

const GOOD = new Set([
  'accelerating', 'growing', 'improving', 'healthy', 'on_track',
  'confirmed', 'strong', 'breakout', 'uptrend', 'recovery',
  'accumulate', 'deploy', 'bounce', 'ready',
])
const MID = new Set([
  'slowing', 'watch', 'mixed', 'cyclical', 'turnaround', 'stalling',
  'close', 'pressured', 'pullback', 'basing', 'hold', 'wait',
])
const BAD = new Set([
  'declining', 'deteriorating', 'broken', 'broken_down', 'failed',
  'avoid', 'exit', 'trim', 'no', 'chase_block', 'downtrend',
  'breakdown',
])

/** State word → green/yellow/red. Unknown words = gray, never green. */
export function toneOf(v: unknown): Tone {
  const s = String(v ?? '').toLowerCase()
  if (!s || s === '—' || s === 'unknown' || s === 'none') return 'off'
  if ([...GOOD].some((g) => s.includes(g))) return 'ok'
  if ([...BAD].some((b) => s.includes(b))) return 'bad'
  if ([...MID].some((m) => s.includes(m))) return 'warn'
  return 'off'
}

function Item({
  label, tone, text, arrow, hint,
}: {
  label: string
  tone: Tone
  text: string
  arrow?: 'up' | 'down' | 'flat' | 'new' | null
  hint?: string
}) {
  const a = arrow
    ? { up: '▲', down: '▼', flat: '●', new: '✦' }[arrow]
    : null
  return (
    <span
      title={hint}
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[tone]}`} />
      <span className="text-[10px] uppercase tracking-wider text-faint">
        {label}
      </span>
      <span className={`text-[11px] font-semibold ${TXT[tone]}`}>
        {text}
      </span>
      {a && <span className={`text-[9px] ${TXT[tone]}`}>{a}</span>}
    </span>
  )
}

/** The glanceable status bar — one chip per decision dimension so a
 *  trader reads the whole name in a second: green = confirmed,
 *  yellow = partial/watch, red = broken/against, gray = unknown. */
export function SignalStrip({
  fundamental, thesis, technical, fvUpside, reviewVerdict,
}: {
  fundamental?: string | null
  thesis?: { status?: string; status_dir?: string } | null
  technical?: string | null
  fvUpside?: number | null
  reviewVerdict?: string | null
}) {
  const fvTone: Tone =
    fvUpside == null ? 'off'
      : fvUpside >= 15 ? 'ok'
        : fvUpside <= -10 ? 'bad'
          : 'warn'
  const fvText =
    fvUpside == null ? 'no model'
      : fvUpside >= 15 ? `cheap +${fvUpside.toFixed(0)}%`
        : fvUpside <= -10 ? `rich ${fvUpside.toFixed(0)}%`
          : 'fair'
  return (
    <div className="flex flex-wrap gap-2">
      <Item label="fundamentals" tone={toneOf(fundamental)}
        text={String(fundamental ?? 'unknown')} />
      <Item label="thesis" tone={toneOf(thesis?.status)}
        text={thesis?.status ? String(thesis.status).replace(/_/g, ' ')
          : 'untracked'}
        arrow={(thesis?.status_dir as 'up' | 'down' | 'flat' | 'new')
          ?? null} />
      <Item label="tape" tone={toneOf(technical)}
        text={String(technical ?? 'unknown')} />
      <Item label="value" tone={fvTone} text={fvText}
        hint="expected fair value vs spot — green cheap, red rich" />
      <Item label="review" tone={toneOf(reviewVerdict)}
        text={String(reviewVerdict ?? 'none')} />
    </div>
  )
}
