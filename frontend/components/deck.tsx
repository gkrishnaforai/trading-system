/** Shared cockpit primitives — the command-deck shell + number
    formatters used by the portfolio and equity pages. Extracted so
    the SEC-health surfaces render the same shell without copying it. */
import React from 'react'

export function money(v?: number | null, dec = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  return `$${Number(v).toLocaleString('en-US',
    { maximumFractionDigits: dec, minimumFractionDigits: dec })}`
}

export function pct(v?: number | null, sign = true, dec = 1) {
  if (v === null || v === undefined || !Number.isFinite(Number(v)))
    return '—'
  const n = Number(v)
  return `${sign && n >= 0 ? '+' : ''}${n.toFixed(dec)}%`
}

export function tone(v?: number | null) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 0 ? 'text-aggressive' : 'text-defensive'
}

/** 0–100 health-score coloring — shared by the table, the book hero
    and the per-symbol page so the bands read identically everywhere. */
export function scoreHealthTone(s?: number | null) {
  const n = Number(s)
  if (!Number.isFinite(n)) return 'text-muted'
  return n >= 65 ? 'text-aggressive'
    : n >= 40 ? 'text-caution' : 'text-defensive'
}

/** Light command-deck hero — the cockpit readout. Soft-paper gradient,
    hairline grid, accent glow edge. */
export function Deck({
  kicker, right, children,
}: {
  kicker: string
  right?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-hairline bg-[#FAF9F7] text-ink shadow-[0_1px_2px_rgba(13,12,10,0.04),0_12px_32px_-16px_rgba(13,12,10,0.12)]">
      {/* glow + grid texture */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 80% at 15% 0%, rgba(234,88,12,0.08), transparent 60%),' +
            'radial-gradient(ellipse 50% 70% at 90% 110%, rgba(15,118,110,0.07), transparent 60%),' +
            'repeating-linear-gradient(0deg, rgba(13,12,10,0.028) 0 1px, transparent 1px 28px),' +
            'repeating-linear-gradient(90deg, rgba(13,12,10,0.028) 0 1px, transparent 1px 28px)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            'linear-gradient(90deg, transparent, rgba(234,88,12,0.55), transparent)',
        }}
      />
      <div className="relative px-6 py-5">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[11px] uppercase tracking-[0.25em] text-faint">
            {kicker}
          </span>
          <span className="font-mono text-[11px] text-faint">{right}</span>
        </div>
        {children}
      </div>
    </div>
  )
}

export function DeckStat({ label, value, toneCls }: {
  label: string; value: string; toneCls?: string
}) {
  return (
    <div className="rounded-lg border border-hairline bg-white/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-faint">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-sm ${toneCls ?? 'text-ink'}`}>
        {value}
      </div>
    </div>
  )
}
