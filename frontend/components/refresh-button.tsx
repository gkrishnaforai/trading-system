'use client'

import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

/** Server-data refresh — router.refresh() re-runs the page's server
    fetches; endpoints wired with `{ fresh: true }` bypass the Data
    Cache so this yields genuinely new tape evals, not a re-render of
    the same snapshot. */
export function RefreshButton({ className }: { className?: string }) {
  const router = useRouter()
  const [pending, start] = useTransition()
  const [clickedAt, setClickedAt] = useState<number | null>(null)
  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        setClickedAt(Date.now())
        start(() => router.refresh())
      }}
      title="Refresh — refetch live data (bypasses the 2-min cache)"
      className={`inline-flex items-center gap-1 rounded-md border border-hairline px-2 py-0.5 text-[10px] font-medium tracking-wider transition-colors ${
        pending
          ? 'text-faint cursor-wait'
          : 'text-muted hover:text-ink hover:border-line cursor-pointer'
      } ${className ?? ''}`}
    >
      <span
        className={`inline-block ${pending ? 'animate-spin' : ''}`}
        style={pending ? { animationDuration: '0.8s' } : undefined}
      >
        ⟳
      </span>
      {pending ? 'refreshing' : 'refresh'}
      {clickedAt != null && !pending && (
        <span className="sr-only">
          refreshed {new Date(clickedAt).toLocaleTimeString()}
        </span>
      )}
    </button>
  )
}
