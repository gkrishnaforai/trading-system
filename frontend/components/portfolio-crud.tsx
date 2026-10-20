'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

const input =
  'rounded-md border border-hairline bg-canvas px-2.5 py-1.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none'
const btn =
  'rounded-full bg-ink px-3.5 py-1.5 text-xs font-medium text-canvas hover:bg-accent transition-colors disabled:opacity-40'

async function call(
  path: string, method: string, body?: unknown,
): Promise<boolean> {
  const res = await fetch(`/api/portfolio/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return res.ok
}

export function BookPicker({ options, selected }: {
  options: { id: string; name: string; holdings_count?: number }[]
  selected?: string | null
}) {
  const router = useRouter()
  return (
    <select
      aria-label="choose portfolio"
      value={selected ?? 'book'}
      onChange={(e) => {
        const v = e.target.value
        router.push(v === 'book' ? '/portfolio' : `/portfolio?p=${v}`)
      }}
      className="rounded-full border border-hairline bg-canvas px-3.5 py-1.5 text-xs font-medium text-ink focus:border-accent focus:outline-none"
    >
      <option value="book">The book</option>
      {options.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
          {p.holdings_count ? ` · ${p.holdings_count}` : ''}
        </option>
      ))}
    </select>
  )
}

export function NewPortfolioForm({ used, limit }: {
  used: number; limit: number
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [capital, setCapital] = useState('100000')
  const [busy, setBusy] = useState(false)
  const router = useRouter()
  const full = used >= limit

  if (!open) {
    return (
      <button
        onClick={() => !full && setOpen(true)}
        disabled={full}
        title={full ? `${limit} portfolios on this plan` : 'new book'}
        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${full
          ? 'border-hairline text-faint'
          : 'border-dashed border-accent/50 text-accent hover:bg-accent/10'
          }`}
      >
        ＋ new book
      </button>
    )
  }
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!name.trim() || busy) return
        setBusy(true)
        const ok = await call('portfolios', 'POST', {
          name: name.trim(),
          portfolio_type: 'custom',
          initial_capital: Number(capital) || 100000,
          currency: 'USD',
        })
        setBusy(false)
        if (ok) { setOpen(false); setName(''); router.refresh() }
      }}
    >
      <input
        className={`${input} w-36`} placeholder="book name"
        value={name} onChange={(e) => setName(e.target.value)} autoFocus
      />
      <input
        className={`${input} w-24`} placeholder="capital"
        value={capital} onChange={(e) => setCapital(e.target.value)}
      />
      <button className={btn} disabled={busy || !name.trim()}>
        {busy ? '…' : 'create'}
      </button>
      <button
        type="button" onClick={() => setOpen(false)}
        className="text-faint hover:text-ink text-sm"
      >✕</button>
    </form>
  )
}

export function AddHoldingForm({ portfolioId }: { portfolioId: string }) {
  const [sym, setSym] = useState('')
  const [shares, setShares] = useState('')
  const [cost, setCost] = useState('')
  const [busy, setBusy] = useState(false)
  const router = useRouter()
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!sym.trim() || busy) return
        setBusy(true)
        const ok = await call(
          `portfolios/${portfolioId}/holdings`, 'POST', {
          symbol: sym.trim().toUpperCase(),
          asset_type: 'stock',
          shares_held: Number(shares) || 0,
          average_cost: Number(cost) || 0,
        })
        setBusy(false)
        if (ok) { setSym(''); setShares(''); setCost(''); router.refresh() }
      }}
    >
      <input
        className={`${input} w-20 font-mono uppercase`} placeholder="SYM"
        value={sym} onChange={(e) => setSym(e.target.value)}
      />
      <input
        className={`${input} w-24`} placeholder="shares"
        value={shares} onChange={(e) => setShares(e.target.value)}
      />
      <input
        className={`${input} w-24`} placeholder="avg cost"
        value={cost} onChange={(e) => setCost(e.target.value)}
      />
      <button className={btn} disabled={busy || !sym.trim()}>
        {busy ? '…' : '＋ add'}
      </button>
    </form>
  )
}

export function HoldingRow({ p, h }: {
  p: string
  h: {
    symbol: string; shares_held?: number; average_cost?: number
    notes?: string | null; company_name?: string | null
  }
}) {
  const [edit, setEdit] = useState(false)
  const [arm, setArm] = useState(false)
  const [shares, setShares] = useState(String(h.shares_held ?? ''))
  const [cost, setCost] = useState(String(h.average_cost ?? ''))
  const [busy, setBusy] = useState(false)
  const router = useRouter()
  const sym = h.symbol.toUpperCase()

  // armed delete auto-reverts — a stray ✕ tap can't leave a loaded gun
  useEffect(() => {
    if (!arm) return
    const t = setTimeout(() => setArm(false), 6000)
    return () => clearTimeout(t)
  }, [arm])

  return (
    <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
      <div className="flex items-center gap-3 min-w-0">
        <Link
          href={`/stock?sym=${encodeURIComponent(sym)}`}
          className="font-semibold text-ink hover:text-accent"
        >
          {sym}
        </Link>
        {h.company_name && (
          <span className="truncate text-xs text-muted">
            {h.company_name}
          </span>
        )}
      </div>
      {edit ? (
        <form
          className="flex items-center gap-2"
          onSubmit={async (e) => {
            e.preventDefault()
            if (busy) return
            setBusy(true)
            const ok = await call(
              `portfolios/${p}/holdings/${sym}`, 'PUT', {
              shares_held: Number(shares) || 0,
              average_cost: Number(cost) || 0,
            })
            setBusy(false)
            if (ok) { setEdit(false); router.refresh() }
          }}
        >
          <input className={`${input} w-24`} value={shares}
            onChange={(e) => setShares(e.target.value)} />
          <input className={`${input} w-24`} value={cost}
            onChange={(e) => setCost(e.target.value)} />
          <button className={btn} disabled={busy}>
            {busy ? '…' : 'save'}
          </button>
          <button type="button" onClick={() => setEdit(false)}
            className="text-faint hover:text-ink">✕</button>
        </form>
      ) : arm ? (
        <div className="flex items-center gap-2.5">
          <span className="text-xs text-defensive">
            remove {sym}?
          </span>
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              const ok = await call(
                `portfolios/${p}/holdings/${sym}`, 'DELETE')
              setBusy(false)
              if (ok) { setArm(false); router.refresh() }
            }}
            className="rounded-full bg-defensive px-2.5 py-0.5 text-[11px] font-semibold text-canvas transition-opacity disabled:opacity-40"
          >
            {busy ? '…' : 'yes'}
          </button>
          <button
            disabled={busy}
            onClick={() => setArm(false)}
            className="text-[11px] font-medium text-faint hover:text-ink"
          >
            no
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 font-mono text-xs text-muted">
          <span>{h.shares_held ?? '—'} sh</span>
          <span>@ ${Number(h.average_cost ?? 0).toFixed(2)}</span>
          <button
            onClick={() => setEdit(true)}
            className="text-faint hover:text-accent"
            title="edit"
          >✎</button>
          <button
            onClick={() => setArm(true)}
            className="text-faint hover:text-defensive"
            title="remove"
          >✕</button>
        </div>
      )}
    </div>
  )
}
