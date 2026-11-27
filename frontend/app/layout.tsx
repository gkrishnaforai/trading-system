import type { Metadata } from 'next'
import Link from 'next/link'
import { Nav } from '@/components/nav'
import './globals.css'

export const metadata: Metadata = {
  title: 'Osprey Desk — See everything. Decide yourself.',
  description:
    'Market cockpit — regime, posture, receipts. The desk sees everything; the call is yours.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-canvas text-ink font-sans antialiased">
        <Nav />
        {children}
        {/* persistent legal disclosure — "not investment advice" must
            be visible on every page, not buried in a linked document */}
        <footer className="border-t border-hairline">
          <div className="mx-auto flex max-w-3xl flex-wrap items-baseline justify-between gap-x-6 gap-y-1 px-5 py-4 text-[11px] text-faint">
            <span>
              Research &amp; education platform — not investment advice.
              Investing involves risk, including loss of principal.
            </span>
            <span className="flex gap-4">
              <Link href="/terms" className="hover:text-ink">Terms</Link>
              <Link href="/terms#affiliate" className="hover:text-ink">
                Affiliate disclosure
              </Link>
              <Link href="/terms#privacy" className="hover:text-ink">
                Privacy
              </Link>
            </span>
          </div>
        </footer>
      </body>
    </html>
  )
}
