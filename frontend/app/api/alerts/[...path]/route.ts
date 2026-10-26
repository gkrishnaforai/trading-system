import { NextRequest, NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

export const dynamic = 'force-dynamic'

/** Thin proxy for the alert inbox — browser calls /api/alerts/*,
 * we forward to the worker's /api/v1/alerts/*. Scan/dismiss are
 * bounded operations (fingerprint dedup), safe pre-auth. */

async function forward(req: NextRequest, path: string[]) {
  const url = `${BASE}/api/v1/alerts/${path.join('/')}${req.nextUrl.search}`
  const init: RequestInit = {
    method: req.method,
    // bounded — a stalled worker must not hold the route open 300s
    signal: AbortSignal.timeout(60_000),
  }
  if (req.method === 'POST' || req.method === 'PUT') {
    init.body = await req.text()
    init.headers = { 'Content-Type': 'application/json' }
  }
  try {
    const res = await fetch(url, init)
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

export async function GET(
  req: NextRequest, ctx: { params: Promise<{ path: string[] }> },
) {
  return forward(req, (await ctx.params).path)
}

export async function POST(
  req: NextRequest, ctx: { params: Promise<{ path: string[] }> },
) {
  return forward(req, (await ctx.params).path)
}
