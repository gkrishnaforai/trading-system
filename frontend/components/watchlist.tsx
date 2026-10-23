'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { SymbolSearch } from '@/components/symbol-search'

const KEY = 'mp_watchlist_v1'

function load(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((s) => typeof s === 'string') : []
  } catch {
    return []
  }
}

function save(list: string[]) {
  localStorage.setItem(KEY, JSON.stringify(list))
  window.dispatchEvent(new Event('mp-watchlist'))
}

export function useWatchlist() {
  const [list, setList] = useState<string[]>([])
  useEffect(() => {
    setList(load())
    const on = () => setList(load())
    window.addEventListener('mp-watchlist', on)
    return () => window.removeEventListener('mp-watchlist', on)
  }, [])
  return list
}

export function isWatched(list: string[], sym: string) {
  return list.includes(sym.toUpperCase())
}

export function toggleWatch(sym: string) {
  const s = sym.toUpperCase()
  const list = load()
  save(list.includes(s) ? list.filter((x) => x !== s) : [...list, s])
}

/** Star toggle — sits on the stock page hero. localStorage until
    per-user watchlists ship with auth (same call site, new backend). */
export function WatchToggle({ sym }: { sym: string }) {
  const list = useWatchlist()
  const on = isWatched(list, sym)
  return (
    <button
      onClick={() => toggleWatch(sym)}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${on
        ? 'border-accent/50 bg-accent/10 text-accent'
        : 'border-hairline text-muted hover:border-accent/40 hover:text-accent'
        }`}
    >
      {on ? '★ watching' : '☆ watch'}
    </button>
  )
}

/** The watchlist section — rendered inside the portfolio page. */
export function WatchlistCard() {
  const list = useWatchlist()
  return (
    <div className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Watchlist
        </span>
        <span className="font-mono text-[11px] text-faint">
          {list.length} names · saved on this device
        </span>
      </div>
      <div className="pt-3">
        <SymbolSearch onPick={(sym) => toggleWatch(sym)} placeholder="add any ticker to watchlist…" />
      </div>
      {list.length === 0 ? (
        <p className="pt-3 text-sm text-muted">
          Empty — search above or open any stock page and tap{' '}
          <span className="text-accent">☆ watch</span>.
        </p>
      ) : (
        <div className="pt-3 flex flex-wrap gap-2">
          {list.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 rounded-full border border-hairline pl-3 pr-1.5 py-1 text-sm"
            >
              <Link
                href={`/stock?sym=${encodeURIComponent(s)}`}
                className="font-medium text-ink hover:text-accent"
              >
                {s}
              </Link>
              <button
                onClick={() => toggleWatch(s)}
                className="text-faint hover:text-defensive px-1"
                aria-label={`remove ${s}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
