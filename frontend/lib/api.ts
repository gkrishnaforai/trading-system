export const BASE =
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

export type Receipt = {
  id?: number
  as_of?: string
  symbol?: string
  action?: string
  instrument?: string
  score?: number
  momentum_state?: string
  posture?: string
  price?: number
  entry?: number
  stop?: number
  target?: number
  r5?: number | null
  r10?: number | null
  r20?: number | null
  r40?: number | null
  r60?: number | null
  mfe?: number | null
  mae?: number | null
}

export type RegimeReceipt = {
  as_of?: string
  stance?: string
  lead_scenario?: string
  spy_ret_20d?: number | null
  spy_ret_60d?: number | null
  lead_correct?: boolean | null
}

export type PulseRow = {
  symbol?: string
  portfolio?: string
  kind?: string
  shares?: number
  avg_cost?: number
  price?: number
  pnl_pct?: number | null
  mom_state?: string
  mom_prev?: string
  fund_state?: string
  revision_grade?: string
  fv_upside?: number | null
  gq_pct?: number
  fwd_pe?: number
  sector?: string
  sector_etf?: string
  sector_flow?: string
  spec?: boolean
  action?: string
  bucket?: string
  why?: string[]
  action_label?: string
  action_confidence?: number
  next_earnings_date?: string
}

export type PulseBook = {
  positions?: number
  cost?: number
  value?: number
  pnl?: number
  pnl_pct?: number | null
  target_pct?: number
  on_pace?: boolean
  track_days?: number
  track_ret_pct?: number
  track_target_pct?: number
  spy_ret_pct?: number
  excess_pct?: number
  goal_month?: number
}

export type AlertItem = {
  id?: string
  symbol?: string
  event_type?: string
  direction?: string
  materiality?: string
  title?: string
  detail?: Record<string, unknown>
  source?: string
  in_portfolio?: boolean
  in_watchlist?: boolean
  status?: string
  priority_score?: number
  created_at?: string
  rating_action?: string
  momentum?: string
  fund_state?: string
  fund_alert?: string
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
  receipts: (limit = 100) =>
    get<{ decisions?: Receipt[]; regime?: RegimeReceipt[] }>(
      `/receipts?limit=${limit}`,
    ),
  portfolioPulse: () =>
    get<{ as_of?: string; rows?: PulseRow[]; book?: PulseBook }>(
      '/portfolio-pulse',
    ),
  strategy: () => get<Record<string, unknown>>('/strategy'),
  conviction: () => get<Record<string, unknown>>('/conviction'),
  convictionHistory: (days = 30) =>
    get<{ rows?: Record<string, unknown>[] }>(
      `/conviction/history?days=${days}`,
    ),
  hiddenGems: () => get<Record<string, unknown>>('/hidden-gems'),
  tailwindCandidates: () =>
    get<Record<string, unknown>>('/tailwind-candidates'),
  dailySheet: () => get<Record<string, unknown>>('/daily-sheet'),
  alerts: (opts: { hours?: number; symbol?: string; status?: string } = {}) =>
    getRaw<{ count?: number; items?: AlertItem[] }>(
      `/api/v1/alerts?hours=${opts.hours ?? 168}` +
      (opts.symbol ? `&symbol=${encodeURIComponent(opts.symbol)}` : '') +
      (opts.status ? `&status=${opts.status}` : ''),
    ),
  stockHealth: (sym: string) =>
    get<Record<string, unknown>>(
      `/symbol/${encodeURIComponent(sym)}/health`,
    ),
  earningsCalendar: (start: string, end: string) =>
    getRaw<{ success?: boolean; count?: number; data?: EarningsRow[] }>(
      `/admin/earnings-calendar?start_date=${start}&end_date=${end}`,
    ),
  posts: (opts: { kind?: string; limit?: number; sym?: string } = {}) =>
    get<{ posts?: PostRow[] }>(
      `/posts?limit=${opts.limit ?? 50}` +
      (opts.kind ? `&kind=${opts.kind}` : '') +
      (opts.sym ? `&sym=${encodeURIComponent(opts.sym)}` : ''),
    ),
  post: (slug: string) => get<Post>(`/posts/${encodeURIComponent(slug)}`),
}

export type PostRow = {
  slug: string
  kind: string
  title: string
  dek?: string
  symbols?: string[]
  as_of?: string
  published_at?: string
}

export type Post = PostRow & { body_md?: string; tier?: string }
