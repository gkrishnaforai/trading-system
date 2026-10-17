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

export type BoardItem = {
  symbol?: string
  action?: string
  score?: number
  momentum?: string
  instrument?: string
  entry_status?: string
  why?: string[]
  gain_pct?: number
  price?: number
  entry?: number
  stop?: number
  target?: number
  days_to_earnings?: number
  in_portfolio?: boolean
  [k: string]: unknown
}

export type DailyBoard = {
  posture?: {
    stance?: string; note?: string; vix?: number;
    spy?: number; spy_vs_200?: number; size_multiplier?: number
  }
  items?: BoardItem[]
  equity?: number
  suggested_tranche?: number
  counts?: Record<string, number>
  as_of?: string
}

export type EarningsRow = {
  symbol?: string
  earnings_date?: string
  [k: string]: unknown
}

async function getRaw<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, {
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
  daily: () => get<DailyBoard>('/daily'),
  stockHealth: (sym: string) =>
    get<Record<string, unknown>>(
      `/symbol/${encodeURIComponent(sym)}/health`,
    ),
  earningsCalendar: (start: string, end: string) =>
    getRaw<{ success?: boolean; count?: number; data?: EarningsRow[] }>(
      `/admin/earnings-calendar?start_date=${start}&end_date=${end}`,
    ),
}
