'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

export function SectorRefreshButton() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  async function refresh() {
    setBusy(true)
    setNote(null)
    try {
      const r = await fetch('/api/admin/refresh/sector-timing', {
        method: 'POST',
      })
      setNote(r.ok ? 'refreshed' : 'refresh failed')
      router.refresh()
    } catch {
      setNote('refresh failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={refresh}
        disabled={busy}
        className="rounded-md border border-hairline px-2 py-0.5 text-[10px] font-mono text-muted hover:text-ink disabled:opacity-50"
      >
        {busy ? '…' : 'refresh'}
      </button>
      {note && <span className="text-[10px] font-mono text-faint">{note}</span>}
    </span>
  )
}
