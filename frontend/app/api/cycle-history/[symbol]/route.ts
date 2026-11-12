import { NextRequest, NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** Cycle-history proxy — the expandable cycle row calls
 * /api/cycle-history/SYM, we forward to the worker's
 * /api/v1/board/cycle/SYM/history server-side so the browser never
 * needs the worker URL directly. */

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params
  try {
    const res = await fetch(
      `${BASE}/api/v1/board/cycle/` +
        `${encodeURIComponent(symbol.toUpperCase())}/history`,
      { signal: AbortSignal.timeout(30_000) })
    const body = await res.text()
    return new NextResponse(body, {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (e) {
    return NextResponse.json(
      { error: `worker unreachable: ${String(e)}` }, { status: 502 })
  }
}
