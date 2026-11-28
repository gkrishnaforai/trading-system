import { NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** MP_DATA_MODE surface — public_only mode shows the SEC-EDGAR
 * disclaimer and hides licensed-data panels. Bounded fetch; a wedged
 * worker must not hold the route open. */
export async function GET() {
  try {
    const res = await fetch(`${BASE}/api/v1/board/data-mode`, {
      signal: AbortSignal.timeout(15_000),
      cache: 'no-store',
    })
    const body = await res.text()
    return new NextResponse(body, {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (e) {
    return NextResponse.json(
      { data_mode: 'full', public_only: false, disclaimer: null,
        error: String(e) }, { status: 200 })
  }
}
