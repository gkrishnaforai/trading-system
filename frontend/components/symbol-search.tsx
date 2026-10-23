'use client'

import { useEffect, useRef, useState } from 'react'

export type StockHit = {
  symbol: string
  company_name: string | null
  exchange: string | null
  sector: string | null
  market_cap: number | null
}

function mc(n: number | null) {
  if (n == null) return ''
  if (n >= 1e12) return `${(n / 1e12).toFixed(1)}T`
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`
  return `${n}`
}

/** Debounced ticker search against the v2 /stocks/search endpoint
    (via the /api/portfolio proxy — auth is handled there). Free-text
    tickers also work: Enter or losing focus emits the raw symbol, so
    names not yet ingested can still be added. */
export function SymbolSearch({
  onPick,
  placeholder = 'Search any ticker or company…',
  accent = false,
}: {
  onPick: (symbol: string, hit?: StockHit) => void
  placeholder?: string
  accent?: boolean
}) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<StockHit[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  useEffect(() => {
    clearTimeout(timer.current)
    const query = q.trim()
    if (query.length < 1) {
      setHits([])
      setOpen(false)
      return
    }
    timer.current = setTimeout(async () => {
      setBusy(true)
      try {
        const res = await fetch(
          `/api/portfolio/stocks/search?query=${encodeURIComponent(query)}`,
        )
        const data = res.ok ? await res.json() : []
        setHits(Array.isArray(data) ? data : [])
        setOpen(true)
      } catch {
        setHits([])
      } finally {
        setBusy(false)
      }
    }, 200)
  }, [q])

  const pick = (symbol: string, hit?: StockHit) => {
    const sym = symbol.toUpperCase()
    setQ('')
    setHits([])
    setOpen(false)
    onPick(sym, hit)
  }

  return (
    <div ref={box} className="relative">
      <div
        className={`flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors ${
          accent
            ? 'border-white/15 bg-white/5 focus-within:border-accent/60'
            : 'border-hairline bg-canvas focus-within:border-accent/60'
        }`}
      >
        <span className={accent ? 'text-white/40' : 'text-faint'}>⌕</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => hits.length > 0 && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && q.trim()) pick(q.trim())
            if (e.key === 'Escape') setOpen(false)
          }}
          placeholder={placeholder}
          className={`w-full bg-transparent font-mono text-sm uppercase outline-none ${
            accent ? 'text-white placeholder-white/30' : 'text-ink placeholder-faint'
          }`}
        />
        {busy && (
          <span
            className={`h-3 w-3 animate-spin rounded-full border-2 border-t-transparent ${
              accent ? 'border-white/30' : 'border-faint/40'
            }`}
          />
        )}
      </div>
      {open && hits.length > 0 && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-hairline bg-canvas shadow-xl">
          {hits.map((h) => (
            <button
              key={h.symbol}
              onClick={() => pick(h.symbol, h)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-elevated"
            >
              <span className="flex items-baseline gap-2 min-w-0">
                <span className="font-mono text-sm font-medium text-ink">
                  {h.symbol}
                </span>
                <span className="truncate text-xs text-faint">
                  {h.company_name ?? '—'}
                </span>
              </span>
              <span className="shrink-0 font-mono text-[11px] text-faint">
                {[h.exchange, h.sector, mc(h.market_cap)]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </button>
          ))}
        </div>
      )}
      {open && !busy && hits.length === 0 && q.trim() && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-hairline bg-canvas px-3 py-2 shadow-xl">
          <button
            onClick={() => pick(q.trim())}
            className="w-full text-left text-xs text-faint hover:text-ink"
          >
            Use <span className="font-mono text-ink">{q.trim().toUpperCase()}</span> — not in the universe yet
          </button>
        </div>
      )}
    </div>
  )
}
