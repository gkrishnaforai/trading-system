import type { Metadata } from 'next'
import { Nav } from '@/components/nav'
import './globals.css'

export const metadata: Metadata = {
  title: 'MarketPulse — Regime',
  description: 'Morning market condition brief — regime, posture, permissions.',
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
      </body>
    </html>
  )
}
