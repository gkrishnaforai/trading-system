'use client'

import { useEffect, useState } from 'react'

/** Reserve bucket + crash playbook — localStorage until auth lands,
 * same swap pattern as the watchlist. */

const RKEY = 'mp_reserve_v1'
const PKEY = 'mp_playbook_v1'

type Entry = { d: string; amt: number; action: 'reserve' | 'deploy' | 'bought' }
type Reserve = { monthly: number; entries: Entry[] }

function loadR(): Reserve {
  try {
    const v = JSON.parse(localStorage.getItem(RKEY) ?? 'null')
    if (v && typeof v === 'object') {
      return { monthly: Number(v.monthly) || 0, entries: Array.isArray(v.entries) ? v.entries : [] }
    }
  } catch { /* fallthrough */ }
  return { monthly: 0, entries: [] }
}

function bucketOf(r: Reserve): number {
  return r.entries.reduce(
    (s, e) => s + (e.action === 'reserve' ? e.amt : e.action === 'deploy' ? -e.amt : 0), 0)
}

export function ReserveTracker({ action }: { action?: string }) {
  const [r, setR] = useState<Reserve>({ monthly: 0, entries: [] })
  useEffect(() => setR(loadR()), [])
  const save = (next: Reserve) => {
    setR(next)
    localStorage.setItem(RKEY, JSON.stringify(next))
  }
  const bucket = bucketOf(r)
  const today = new Date().toISOString().slice(0, 10)

  function add(act: Entry['action'], amt?: number) {
    const a = amt ?? r.monthly
    if (!a) return
    save({ ...r, entries: [...r.entries, { d: today, amt: a, action: act }] })
  }

  return (
    <div className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Reserve bucket
        </span>
        <span className="font-mono text-[11px] text-faint">on this device</span>
      </div>
      <div className="pt-3 flex items-baseline gap-6">
        <div>
          <div className="font-mono text-2xl text-ink">
            ${bucket.toLocaleString()}
          </div>
          <div className="text-[11px] text-faint">in reserve</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-faint">monthly</span>
          <input
            type="number"
            className="w-24 rounded-md border border-hairline bg-canvas px-2 py-1 font-mono text-sm text-ink"
            placeholder="500"
            value={r.monthly || ''}
            onChange={(e) => save({ ...r, monthly: Number(e.target.value) || 0 })}
          />
        </div>
      </div>
      <div className="pt-3 flex flex-wrap gap-2">
        <button
          onClick={() => add('reserve')}
          className="rounded-full border border-defensive/50 px-3 py-1 text-xs font-medium text-defensive hover:bg-defensive/10"
        >
          → reserve this month's ${r.monthly || '?'}
        </button>
        {bucket > 0 && (
          <button
            onClick={() => add('deploy', bucket)}
            className="rounded-full border border-aggressive/50 px-3 py-1 text-xs font-medium text-aggressive hover:bg-aggressive/10"
          >
            deploy ${bucket.toLocaleString()}
          </button>
        )}
        <button
          onClick={() => add('bought')}
          className="rounded-full border border-hairline px-3 py-1 text-xs font-medium text-muted hover:border-accent/40 hover:text-accent"
        >
          bought as planned
        </button>
      </div>
      {action === 'deploy' && bucket > 0 && (
        <p className="pt-3 text-[12px] text-aggressive">
          regime flipped — the reserve is what this moment is for.
        </p>
      )}
      {r.entries.length > 0 && (
        <div className="pt-3 space-y-1">
          {r.entries.slice(-5).reverse().map((e, i) => (
            <div key={i} className="flex justify-between font-mono text-[11px] text-faint">
              <span>{e.d}</span>
              <span className={
                e.action === 'reserve' ? 'text-defensive'
                : e.action === 'deploy' ? 'text-aggressive' : 'text-muted'
              }>
                {e.action === 'reserve' ? '+' : e.action === 'deploy' ? '−' : ''}
                ${e.amt.toLocaleString()} {e.action}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function CrashPlaybook({ defensive }: { defensive: boolean }) {
  const [plan, setPlan] = useState('')
  const [editing, setEditing] = useState(false)
  useEffect(() => {
    setPlan(localStorage.getItem(PKEY) ?? '')
  }, [])

  return (
    <div className={`rounded-xl border px-5 py-4 ${defensive
      ? 'border-accent/60 bg-accent/[0.05]'
      : 'border-hairline bg-card'}`}>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Crash playbook
        </span>
        {defensive && (
          <span className="rounded-full border border-accent/50 px-2 py-0.5 text-[10px] font-semibold text-accent">
            live — read your plan
          </span>
        )}
      </div>
      {plan && !editing ? (
        <>
          <p className="pt-3 whitespace-pre-wrap text-[14px] leading-relaxed text-ink">
            {plan}
          </p>
          <button
            onClick={() => setEditing(true)}
            className="pt-2 text-[11px] text-faint hover:text-accent"
          >
            edit
          </button>
        </>
      ) : (
        <>
          <p className="pt-3 text-[13px] leading-relaxed text-muted">
            Write it while you're calm — it shows up here when the tape
            is broken and your amygdala is running the account.
            Example: <em>"I pause new buys, keep the reserve, and sell
            nothing for 60 days. Drawdowns under 25% are normal."</em>
          </p>
          <textarea
            className="mt-3 w-full rounded-md border border-hairline bg-canvas px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
            rows={4}
            placeholder="When the regime turns defensive, I will…"
            value={plan}
            onChange={(e) => setPlan(e.target.value)}
          />
          <button
            onClick={() => {
              localStorage.setItem(PKEY, plan)
              setEditing(false)
            }}
            className="mt-2 rounded-full bg-ink px-4 py-1.5 text-xs font-medium text-canvas hover:bg-accent"
          >
            save the plan
          </button>
        </>
      )}
    </div>
  )
}
