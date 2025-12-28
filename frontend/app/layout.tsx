import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Trading System',
  description: 'AI-powered trading system',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
