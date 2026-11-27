import { NextRequest, NextResponse } from 'next/server'
import { BASE } from '@/lib/api'

/** /api/brain — proxy to the worker's brain endpoints.
    GET            → GET  /api/v1/board/brain        (vitals + today + evolution)
    GET ?part=queue→ GET  /api/v1/board/brain/intake (full queue rows)
    POST           → POST /api/v1/board/brain/intake (submit a doc) */
export async function GET(req: NextRequest) {
  const part = req.nextUrl.searchParams.get('part')
  const path = part === 'queue'
    ? '/api/v1/board/brain/intake'
    : '/api/v1/board/brain'
  try {
    const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch (e) {
    return NextResponse.json(
      { error: `worker unreachable: ${String(e)}` }, { status: 502 })
  }
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  try {
    const res = await fetch(`${BASE}/api/v1/board/brain/intake`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch (e) {
    return NextResponse.json(
      { error: `worker unreachable: ${String(e)}` }, { status: 502 })
  }
}
