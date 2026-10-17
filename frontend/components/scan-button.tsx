'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

/** "Scan now" — kicks the catalyst scan, polls status until it
 * finishes, then refreshes the server-rendered inbox. */
export function ScanButton({ running }: { running: boolean }) {
  const [busy, setBusy] = useState(running)
  const router = useRouter()
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [])

  async function kick() {
    if (busy) return
    setBusy(true)
    await fetch('/api/alerts/scan', { method: 'POST', body: '{}' })
    poll()
  }

  async function poll() {
    try {
      const res = await fetch('/api/alerts/scan/status')
      const j = await res.json()
      if (j.running) {
        timer.current = setTimeout(poll, 4000)
        return
      }
    } catch { /* fallthrough — refresh anyway */ }
    setBusy(false)
    router.refresh()
  }

  return (
    <button
      onClick={kick}
      disabled={busy}
      className="rounded-full border border-accent/50 px-3.5 py-1.5 text-xs font-semibold text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
    >
      {busy ? 'scanning…' : 'scan now'}
    </button>
  )
}
