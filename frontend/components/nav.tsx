'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

const LINKS = [
  { href: '/', label: 'Regime' },
  { href: '/calendar', label: 'Calendar' },
  { href: '/board', label: 'Board' },
  { href: '/themes', label: 'Themes' },
  { href: '/cycle', label: 'Cycle' },
  { href: '/etf', label: 'ETF' },
  { href: '/readiness', label: 'Ready' },
  { href: '/plan', label: 'Plan' },
  { href: '/receipts', label: 'Receipts' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/desk', label: 'Desk' },
  { href: '/insights', label: 'Insights' },
  { href: '/alerts', label: 'Alerts' },
  { href: '/hold', label: 'Hold' },
  { href: '/apis', label: 'APIs' },
]

export function Nav() {
  const path = usePathname()
  const router = useRouter()
  const [role, setRole] = useState<string | null>(null)
  const [verified, setVerified] = useState<boolean | null>(null)
  const [resent, setResent] = useState(false)
  const [dataMode, setDataMode] = useState<{
    public_only: boolean; disclaimer: string | null
  } | null>(null)
  useEffect(() => {
    fetch('/api/me')
      .then((r) => r.json())
      .then((u) => {
        setRole(u?.role ?? null)
        setVerified(u?.emailVerified ?? null)
      })
      .catch(() => { })
    fetch('/api/data-mode')
      .then((r) => r.json())
      .then(setDataMode)
      .catch(() => { })
  }, [])

  async function signOut() {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => { })
    router.push('/login')
    router.refresh()
  }

  async function resend() {
    const r = await fetch('/api/auth/resend', { method: 'POST' })
      .catch(() => null)
    if (r?.ok) setResent(true)
  }

  if (path.startsWith('/login') || path.startsWith('/signup') ||
      path.startsWith('/verify')) {
    return null
  }

  const isAdmin = role === 'admin'
  // mirror the middleware role map — Group-2 advisory surfaces are
  // admin-only; advanced/super-user see the factual read surfaces
  const links = isAdmin
    ? LINKS
    : role === 'advanced' || role === 'super-user'
      ? LINKS.filter((l) => ['/portfolio', '/calendar'].includes(l.href))
      : role === 'basic'
        ? LINKS.filter((l) => l.href === '/portfolio')
        : []

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
          {links.map((l) => {
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
              href="/brain"
              className={`relative px-2 py-1.5 text-[12.5px] font-medium transition-colors ${path.startsWith('/brain') ? 'text-accent' : 'text-muted hover:text-ink'
                }`}
            >
              Brain
              {path.startsWith('/brain') && (
                <span className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-accent" />
              )}
            </Link>
          )}
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
          {role && role !== 'anonymous' && (
            <button
              onClick={signOut}
              className="ml-1 px-2 py-1.5 text-[12.5px] font-medium text-faint transition-colors hover:text-ink"
            >
              Sign out
            </button>
          )}
        </div>
      </div>
      {dataMode?.public_only && (
        <div className="border-t border-hairline bg-panel/60 px-5 py-1.5 text-center text-[11.5px] text-faint">
          {dataMode.disclaimer}
        </div>
      )}
      {role && role !== 'anonymous' && verified === false && (
        <div className="border-t border-caution/30 bg-caution/[0.07] px-5 py-1.5 text-center text-[12px] text-caution">
          {resent
            ? 'Verification email sent — check your inbox.'
            : (
              <>
                Your email isn&apos;t verified yet — check your inbox
                for the link, or{' '}
                <button
                  onClick={resend}
                  className="font-semibold underline underline-offset-2 hover:text-ink"
                >
                  resend it
                </button>
                .
              </>
            )}
        </div>
      )}
    </nav>
  )
}
