'use client'

import { useState } from 'react'

/** Interactive runner for POST endpoints on the APIs page — fills
    the path template, POSTs through the /api/admin proxy, shows the
    response inline. GET entries render as plain links instead. */
export function ApiRunner({
  method, path, fields,
}: {
  method: string
  path: string
  fields?: { name: string; placeholder?: string }[]
}) {
  const [vals, setVals] = useState<Record<string, string>>({})
  const [out, setOut] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  function filled() {
    let p = path
    const qs: string[] = []
    for (const f of fields ?? []) {
      const v = (vals[f.name] ?? '').trim()
      if (!v) continue
      if (p.includes(`{${f.name}}`)) {
        p = p.replace(`{${f.name}}`, encodeURIComponent(v))
      } else {
        qs.push(`${f.name}=${encodeURIComponent(v)}`)
      }
    }
    return p + (qs.length ? `${p.includes('?') ? '&' : '?'}${qs.join('&')}` : '')
  }

  async function run() {
    setBusy(true)
    setOut(null)
    setErr(null)
    try {
      const res = await fetch(`/api/admin/${filled()}`, { method })
      const text = await res.text()
      try {
        setOut(JSON.stringify(JSON.parse(text), null, 2).slice(0, 4000))
      } catch {
        setOut(text.slice(0, 4000))
      }
      if (!res.ok) setErr(`HTTP ${res.status}`)
    } catch {
      setErr('request failed — worker unreachable?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pt-2">
      <div className="flex flex-wrap items-center gap-2">
        {(fields ?? []).map(f => (
          <input
            key={f.name}
            value={vals[f.name] ?? ''}
            onChange={e => setVals(v => ({ ...v, [f.name]: e.target.value }))}
            placeholder={f.placeholder ?? f.name}
            className="w-40 rounded border border-hairline bg-canvas px-2 py-1 font-mono text-xs text-ink placeholder:text-faint"
          />
        ))}
        <button
          onClick={run}
          disabled={busy}
          className="rounded border border-accent/40 bg-accent/10 px-3 py-1 font-mono text-xs font-semibold text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          {busy ? 'running…' : `run ${method}`}
        </button>
        <span className="font-mono text-[10px] text-faint break-all">
          /api/admin/{filled()}
        </span>
      </div>
      {err && <div className="pt-1 font-mono text-[11px] text-defensive">{err}</div>}
      {out && (
        <pre className="mt-2 max-h-64 overflow-auto rounded border border-hairline bg-canvas p-2 font-mono text-[10px] leading-relaxed text-muted">
          {out}
        </pre>
      )}
    </div>
  )
}
