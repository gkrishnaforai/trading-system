import { NextResponse } from 'next/server'
import { getUser } from '@/lib/auth'

export const dynamic = 'force-dynamic'

/** Who am I — lets client components (nav) render role-gated chrome
    without exposing the httpOnly token. */
export async function GET() {
  const u = await getUser()
  return NextResponse.json(u)
}
