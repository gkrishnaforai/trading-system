'use client'

import { useState } from 'react'

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

export function Kv({ k, v }: { k: string; v: unknown }) {
  return (
    <div className="flex justify-between gap-4 border-b border-hairline/60 py-2 text-sm last:border-0">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-ink text-right">
        {v === null || v === undefined
          ? '—'
          : typeof v === 'object'
            ? JSON.stringify(v)
            : String(v)}
      </span>
    </div>
  )
}
