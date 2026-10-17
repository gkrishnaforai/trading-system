'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const LINKS = [
  { href: '/', label: 'Market Regime' },
  { href: '/calendar', label: "Today's Calendar" },
  { href: '/board', label: 'Daily Board' },
]

export function Nav() {
  const path = usePathname()
  return (
    <nav className="sticky top-0 z-20 border-b border-hairline bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-3.5">
        <Link
          href="/"
          className="text-[13px] font-semibold tracking-[0.28em] text-ink"
        >
          MARKET<span className="text-accent">PULSE</span>
        </Link>
        <div className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active =
              l.href === '/' ? path === '/' : path.startsWith(l.href)
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`relative px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  active ? 'text-accent' : 'text-muted hover:text-ink'
                }`}
              >
                {l.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-accent" />
                )}
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
