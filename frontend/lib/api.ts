const BASE =
  process.env.WORKER_URL ||
  process.env.NEXT_PUBLIC_WORKER_URL ||
  'http://localhost:8001'

export type Posture = {
  posture?: string
  matched?: string
  new_longs?: boolean
  shorts?: boolean
  hedge_on?: boolean
  regime_as_of?: string
  note?: string
  instruments?: { short?: { etf?: string; note?: string } }
  stats?: Array<Record<string, unknown>>
}

export type MorningRegime = {
  today?: {
    as_of?: string
    regime?: string
    ai_regime?: string
    score?: number
    confidence?: number
    buckets?: Record<string, unknown> | unknown[]
    llm?: unknown
    verdict?: string
    horizon_1m?: unknown
    horizon_3m?: unknown
  } | null
  record?: Array<Record<string, unknown>>
}

export type MacroEvent = {
  title?: string
  name?: string
  when?: string
  date?: string
  importance?: string
  rescheduled?: boolean
  rescheduled_from?: string
  verified?: boolean
  unconfirmed?: boolean
  days_away?: number
  actual?: number
  estimate?: number
  prev?: number
  reading?: string
  impact?: string
  source_url?: string
  judge?: {
    verdict?: string
    confidence?: number
    thesis?: string
    spy_ret?: number
    correct?: boolean
  }
  [k: string]: unknown
}

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}/api/v1/board${path}`, {
      next: { revalidate: 120 },
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

export const api = {
  posture: () => get<Posture>('/posture'),
  morningRegime: () => get<MorningRegime>('/morning-regime'),
  macroEvents: () =>
    get<{ events?: MacroEvent[] } | MacroEvent[]>('/macro-events'),
}
