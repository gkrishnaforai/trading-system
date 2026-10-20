import { NextRequest, NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

/** POST /api/plan — proxy to the worker's trade-plans endpoints.
    {action:'open', symbol, use_case, entry_px, thesis, ...}
      → POST /api/v1/board/trade-plans
    {action:'close', id, close_px, reason}
      → POST /api/v1/board/trade-plans/{id}/close
    Advisory bookkeeping only — nothing here touches a broker. */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  const action = body.action
  let path: string
  let payload: Record<string, unknown>
  if (action === 'open') {
    path = '/api/v1/board/trade-plans'
    payload = {
      symbol: body.symbol, use_case: body.use_case,
      entry_px: body.entry_px, entry_date: body.entry_date,
      stop_px: body.stop_px, target1_px: body.target1_px,
      target2_px: body.target2_px, thesis: body.thesis,
      qty: body.qty,
    }
  } else if (action === 'close') {
    path = `/api/v1/board/trade-plans/${body.id}/close`
    payload = { close_px: body.close_px, reason: body.reason }
  } else {
    return NextResponse.json({ error: 'unknown action' },
      { status: 400 })
  }
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    })
    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    return NextResponse.json(
      { error: 'worker unreachable' }, { status: 502 })
  }
}
