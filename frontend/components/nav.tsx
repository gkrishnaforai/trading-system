'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

const LINKS = [
  { href: '/', label: 'Regime' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/board', label: 'Board' },
  { href: '/plan', label: 'Plan' },
  { href: '/receipts', label: 'Receipts' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/desk', label: 'Desk' },
  { href: '/insights', label: 'Insights' },
  { href: '/alerts', label: 'Alerts' },
  { href: '/hold', label: 'Hold' },
]

export function Nav() {
  const path = usePathname()
  const [isAdmin, setIsAdmin] = useState(false)
  useEffect(() => {
    fetch('/api/me')
      .then((r) => r.json())
      .then((u) => setIsAdmin(u?.role === 'admin'))
      .catch(() => { })
  }, [])
  return (
    <nav className="sticky top-0 z-20 border-b border-hairline bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-3.5">
        <Link
          href="/"
          className="text-[13px] font-semibold tracking-[0.28em] text-ink"
        >
          OSPREY<span className="text-accent">DESK</span>
        </Link>
        <div className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active =
              l.href === '/' ? path === '/' : path.startsWith(l.href)
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`relative px-2 py-1.5 text-[12.5px] font-medium transition-colors ${active ? 'text-accent' : 'text-muted hover:text-ink'
                  }`}
              >
                {l.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-accent" />
                )}
              </Link>
            )
          })}
          {isAdmin && (
            <Link
              href="/admin"
              className={`relative px-2 py-1.5 text-[12.5px] font-medium transition-colors ${path.startsWith('/admin') ? 'text-accent' : 'text-muted hover:text-ink'
                }`}
            >
              Admin
              {path.startsWith('/admin') && (
                <span className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-accent" />
              )}
            </Link>
          )}
        </div>
      </div>
    </nav>
  )
}
