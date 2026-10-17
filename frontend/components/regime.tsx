import { canSee, tierLabel } from '@/lib/tier'

export function Chevron() {
  return (
    <span className="chevron text-faint select-none" aria-hidden>
      ›
    </span>
  )
}

export function Section({
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details
      open={defaultOpen}
      className="group border-t border-hairline py-5"
    >
      <summary className="flex items-baseline justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <Chevron />
          <h2 className="text-sm font-medium tracking-wide uppercase text-muted">
            {title}
          </h2>
        </div>
        {subtitle && (
          <span className="text-xs text-faint font-mono">{subtitle}</span>
        )}
      </summary>
      <div className="pt-5 pl-6">{children}</div>
    </details>
  )
}

export function Chip({
  label,
  on,
  tone,
}: {
  label: string
  on?: boolean
  tone?: 'ok' | 'warn' | 'off'
}) {
  const t =
    tone ??
    (on === undefined ? 'warn' : on ? 'ok' : 'off')
  const styles = {
    ok: 'border-aggressive/40 text-aggressive',
    warn: 'border-caution/40 text-caution',
    off: 'border-faint text-muted line-through decoration-faint/60',
  }[t]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium tracking-wide ${styles}`}
    >
      {label}
    </span>
  )
}

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-faint">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm text-ink">{value}</div>
    </div>
  )
}

function fmtNum(n: number) {
  if (!Number.isFinite(n)) return String(n)
  return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

const isScalar = (v: unknown) =>
  v === null || v === undefined ||
  typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'

function scalarText(v: unknown) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return fmtNum(v)
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  return String(v)
}

/** Compact one-liner — used in table cells, chips, labels. */
export function fmtShort(v: unknown, depth = 0): string {
  if (isScalar(v)) return scalarText(v)
  if (depth > 2) return '…'
  if (Array.isArray(v)) {
    if (!v.length) return '—'
    return v.map((x) => fmtShort(x, depth + 1)).join(' · ')
  }
  if (typeof v === 'object') {
    const parts = Object.entries(v as Record<string, unknown>)
      .filter(([, x]) => x !== null && x !== undefined)
      .map(([k, x]) => `${k.replace(/_/g, ' ')} ${fmtShort(x, depth + 1)}`)
    return parts.length ? parts.join(' · ') : '—'
  }
  return String(v)
}

/** Recursive readable renderer — objects become key/value rows,
    arrays become '·' items or bullet lists. No raw JSON anywhere. */
export function Val({ v, depth = 0 }: { v: unknown; depth?: number }) {
  if (isScalar(v)) {
    return (
      <span className={v === null || v === undefined ? 'text-faint' : 'text-ink'}>
        {scalarText(v)}
      </span>
    )
  }
  if (Array.isArray(v)) {
    if (!v.length) return <span className="text-faint">—</span>
    if (v.every(isScalar)) {
      return (
        <span className="text-ink">
          {v.map(scalarText).join(' · ')}
        </span>
      )
    }
    return (
      <ul className="space-y-1">
        {v.map((x, i) => (
          <li key={i} className="flex gap-1.5">
            <span className="text-faint">·</span>
            <Val v={x} depth={depth + 1} />
          </li>
        ))}
      </ul>
    )
  }
  const entries = Object.entries(v as Record<string, unknown>)
    .filter(([, x]) => x !== null && x !== undefined && x !== '')
  if (!entries.length) return <span className="text-faint">—</span>
  return (
    <div className={depth > 0 ? 'pl-3 border-l-2 border-hairline/70' : ''}>
      {entries.map(([k, x]) => (
        <div key={k} className="flex justify-between items-baseline gap-4 py-0.5">
          <span className="text-muted shrink-0">{k.replace(/_/g, ' ')}</span>
          <span className="text-right min-w-0">
            <Val v={x} depth={depth + 1} />
          </span>
        </div>
      ))}
    </div>
  )
}

/** Tier gate — renders children when the current tier allows, else a
    subscribe teaser. Auth isn't wired yet (currentTier() = pro), so
    this annotates the sections for the day it is. */
export function Gate({
  feature,
  children,
}: {
  feature: string
  children: React.ReactNode
}) {
  if (canSee(feature)) return <>{children}</>
  return (
    <div className="rounded-xl border border-dashed border-accent/50 bg-accent/[0.04] px-5 py-6 text-center">
      <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-accent">
        {tierLabel(feature)}
      </div>
      <p className="pt-2 text-sm text-muted">
        This section is part of the {tierLabel(feature)} plan.
      </p>
    </div>
  )
}

export function Kv({ k, v }: { k: string; v: unknown }) {
  const simple = isScalar(v) ||
    (Array.isArray(v) && v.every(isScalar))
  if (simple) {
    return (
      <div className="flex justify-between gap-4 border-b border-hairline/60 py-2 text-sm last:border-0">
        <span className="text-muted">{k}</span>
        <span className="font-mono text-ink text-right">
          <Val v={v} />
        </span>
      </div>
    )
  }
  return (
    <div className="border-b border-hairline/60 py-2 text-sm last:border-0">
      <div className="text-muted pb-1">{k}</div>
      <Val v={v} depth={1} />
    </div>
  )
}
