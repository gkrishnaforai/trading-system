'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

export function RetryRefresh() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  return (
    <button
      onClick={() => {
        setBusy(true)
        router.refresh()
        setTimeout(() => setBusy(false), 1500)
      }}
      className="font-medium text-accent hover:underline disabled:opacity-40"
      disabled={busy}
    >
      {busy ? '…' : 'retry'}
    </button>
  )
}
