'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { SymbolSearch } from '@/components/symbol-search'

const input =
  'rounded-lg border border-hairline bg-canvas px-2.5 py-1.5 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none transition-colors'
const btn =
  'rounded-full bg-ink px-3.5 py-1.5 text-xs font-medium text-canvas hover:bg-accent transition-colors disabled:opacity-40'

type CallResult = { ok: boolean; error?: string }

async function call(
  path: string, method: string, body?: unknown,
): Promise<CallResult> {
  try {
    const res = await fetch(`/api/portfolio/${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (res.ok) return { ok: true }
    let detail = ''
    try {
      const j = await res.json()
      detail = j?.detail ?? j?.error ?? ''
    } catch { /* non-json body */ }
    return { ok: false, error: detail || `request failed (${res.status})` }
  } catch {
    return { ok: false, error: 'network error — is the cockpit up?' }
  }
}

/** Book rail — every book as a card chip; the system book first. */
/** Book picker — a compact select instead of the horizontal card
    rail. Keeps "The book" as the aggregate first option. */
export function BookSelect({ options, selected }: {
  options: {
    id: string; name: string; portfolio_type?: string
    holdings_count?: number
  }[]
  selected?: string | null
}) {
  const router = useRouter()
  return (
    <div className="relative flex-1 min-w-0">
      <select
        value={selected ?? ''}
        onChange={(e) => {
          const v = e.target.value
          router.push(v ? `/portfolio?p=${v}` : '/portfolio')
        }}
        className="w-full appearance-none rounded-xl border border-hairline bg-card px-3.5 py-2.5 pr-9 text-sm font-medium text-ink shadow-[0_0_0_1px_rgba(234,88,12,0.12)] focus:border-accent focus:outline-none transition-colors"
      >
        <option value="">
          The book — all positions ({options.length} books)
        </option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} · {p.portfolio_type ?? 'book'} ·{' '}
            {p.holdings_count ?? 0} pos
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[10px] text-faint">
        ▾
      </span>
    </div>
  )
}

export function BookRail({ options, selected }: {
  options: {
    id: string; name: string; portfolio_type?: string
    holdings_count?: number; total_invested?: number
  }[]
  selected?: string | null
}) {
  const card = (active: boolean) =>
    `group flex min-w-[9rem] flex-col gap-0.5 rounded-xl border px-3.5 py-2.5 transition-all ${active
      ? 'border-accent/60 bg-accent/[0.06] shadow-[0_0_0_1px_rgba(234,88,12,0.25),0_4px_18px_-6px_rgba(234,88,12,0.35)]'
      : 'border-hairline bg-card hover:border-faint/60 hover:shadow-sm'
    }`
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      <Link href="/portfolio" className={card(!selected)}>
        <span className="text-sm font-medium text-ink">The book</span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
          system · all books
        </span>
      </Link>
      {options.map((p) => (
        <Link
          key={p.id}
          href={`/portfolio?p=${p.id}`}
          className={card(selected === p.id)}
        >
          <span className="truncate text-sm font-medium text-ink">
            {p.name}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
            {p.portfolio_type ?? 'book'} · {p.holdings_count ?? 0} pos
          </span>
        </Link>
      ))}
    </div>
  )
}

export function NewPortfolioForm({ used, limit }: {
  used: number; limit: number
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [capital, setCapital] = useState('100000')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const router = useRouter()
  const full = used >= limit

  if (!open) {
    return (
      <button
        onClick={() => !full && setOpen(true)}
        disabled={full}
        title={full ? `${limit} portfolios on this plan` : 'new book'}
        className={`flex min-w-[9rem] flex-col items-center justify-center gap-0.5 rounded-xl border border-dashed px-3.5 py-2.5 text-xs font-medium transition-colors ${full
          ? 'border-hairline text-faint'
          : 'border-accent/50 text-accent hover:bg-accent/[0.06]'
          }`}
      >
        <span className="text-base leading-none">＋</span>
        <span>new book</span>
      </button>
    )
  }
  return (
    <form
      className="flex items-center gap-2 rounded-xl border border-accent/40 bg-accent/[0.04] px-3.5 py-2.5"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!name.trim() || busy) return
        setBusy(true)
        setErr(null)
        const res = await call('portfolios', 'POST', {
          name: name.trim(),
          portfolio_type: 'custom',
          initial_capital: Number(capital) || 100000,
          currency: 'USD',
        })
        setBusy(false)
        if (res.ok) {
          setOpen(false); setName('')
          router.refresh()
        } else {
          setErr(res.error ?? 'create failed')
        }
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
      {err && (
        <span className="max-w-[16rem] truncate text-xs text-defensive" title={err}>
          {err}
        </span>
      )}
    </form>
  )
}

/** Add any stock to this book — search the universe or type a raw ticker. */
export function AddHoldingForm({ portfolioId }: { portfolioId: string }) {
  const [sym, setSym] = useState('')
  const [shares, setShares] = useState('')
  const [cost, setCost] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const router = useRouter()

  const submit = async () => {
    if (!sym.trim() || busy) return
    setBusy(true)
    setErr(null)
    const res = await fetch(
      `/api/portfolio/portfolios/${portfolioId}/holdings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: sym.trim().toUpperCase(),
        asset_type: 'stock',
        shares_held: Number(shares) || 0,
        average_cost: Number(cost) || 0,
      }),
    })
    setBusy(false)
    if (res.ok) {
      setSym(''); setShares(''); setCost('')
      router.refresh()
    } else {
      setErr(`add failed (${res.status})`)
    }
  }

  return (
    <div className="rounded-xl border border-hairline bg-card px-4 py-3.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Add a position
        </span>
        {sym && (
          <span className="font-mono text-[11px] text-accent">{sym}</span>
        )}
      </div>
      <div className="pt-2.5">
        <SymbolSearch
          onPick={(s) => setSym(s)}
          placeholder={sym || 'search ticker or company…'}
        />
      </div>
      <form
        className="flex flex-wrap items-center gap-2 pt-2.5"
        onSubmit={(e) => { e.preventDefault(); submit() }}
      >
        <input
          className={`${input} w-24`} placeholder="shares"
          value={shares} onChange={(e) => setShares(e.target.value)}
        />
        <input
          className={`${input} w-28`} placeholder="avg cost $"
          value={cost} onChange={(e) => setCost(e.target.value)}
        />
        <button className={btn} disabled={busy || !sym.trim()}>
          {busy ? '…' : `＋ add ${sym || ''}`}
        </button>
        {err && <span className="text-xs text-defensive">{err}</span>}
      </form>
    </div>
  )
}

/** System-book entry point to holdings CRUD — pick a target book,
    then the same add-position form. The union "book" view stays
    read-only; positions live inside a book. */
export function AddPositionDock({ books }: {
  books: { id: string; name: string }[]
}) {
  const [target, setTarget] = useState(books[0]?.id ?? '')
  if (books.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-hairline px-5 py-4 text-xs text-muted">
        No books yet — hit <span className="text-accent">＋ new book</span>{' '}
        above, then add positions to it here.
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Add to
        </span>
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="rounded-md border border-hairline bg-canvas px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none"
        >
          {books.map((b) => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </div>
      <AddHoldingForm key={target} portfolioId={target} />
    </div>
  )
}

/** Armed delete for a book — two taps, auto-disarms, routes home. */
export function DeleteBookButton({ id, name }: { id: string; name: string }) {
  const [arm, setArm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const router = useRouter()

  useEffect(() => {
    if (!arm) return
    const t = setTimeout(() => setArm(false), 6000)
    return () => clearTimeout(t)
  }, [arm])

  if (arm) {
    return (
      <span className="inline-flex items-center gap-2.5">
        <span className="text-xs text-defensive">
          delete “{name}” + its positions?
        </span>
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            setErr(null)
            const res = await call(`portfolios/${id}`, 'DELETE')
            setBusy(false)
            if (res.ok) {
              router.push('/portfolio')
              router.refresh()
            } else {
              setErr(res.error ?? 'delete failed')
              setArm(false)
            }
          }}
          className="rounded-full bg-defensive px-2.5 py-0.5 text-[11px] font-semibold text-canvas disabled:opacity-40"
        >
          {busy ? '…' : 'yes, delete'}
        </button>
        <button
          disabled={busy}
          onClick={() => setArm(false)}
          className="text-[11px] font-medium text-faint hover:text-ink"
        >
          no
        </button>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={() => setArm(true)}
        className="text-[11px] font-medium text-faint hover:text-defensive transition-colors"
      >
        delete book
      </button>
      {err && <span className="text-[11px] text-defensive">{err}</span>}
    </span>
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
  const [err, setErr] = useState<string | null>(null)
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
          className="font-mono text-sm font-semibold text-ink hover:text-accent"
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
            setErr(null)
            const res = await call(
              `portfolios/${p}/holdings/${sym}`, 'PUT', {
              shares_held: Number(shares) || 0,
              average_cost: Number(cost) || 0,
            })
            setBusy(false)
            if (res.ok) {
              setEdit(false)
              router.refresh()
            } else {
              setErr(res.error ?? 'save failed')
            }
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
          {err && (
            <span className="max-w-[14rem] truncate text-xs text-defensive" title={err}>
              {err}
            </span>
          )}
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
              setErr(null)
              const res = await call(
                `portfolios/${p}/holdings/${sym}`, 'DELETE')
              setBusy(false)
              if (res.ok) {
                setArm(false)
                router.refresh()
              } else {
                setErr(res.error ?? 'delete failed')
              }
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
          {err && (
            <span className="max-w-[12rem] truncate text-xs text-defensive" title={err}>
              {err}
            </span>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3 font-mono text-xs text-muted">
          <span>{h.shares_held ?? '—'} sh</span>
          <span>@ ${Number(h.average_cost ?? 0).toFixed(2)}</span>
          <button
            onClick={() => setEdit(true)}
            className="font-sans text-[11px] font-medium text-faint hover:text-accent"
          >edit</button>
          <button
            onClick={() => setArm(true)}
            className="font-sans text-[11px] font-medium text-faint hover:text-defensive"
          >remove</button>
        </div>
      )}
    </div>
  )
}
