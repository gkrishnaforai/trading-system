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
  bias?: string
  vol?: { vix?: number | null; vxn?: number | null; vxn_chg_5d?: number | null }
}

export type HorizonScenario = {
  base?: string
  bear?: string
  bull?: string
  stress?: string
  windows?: string[]
  key_catalyst?: string
}

export type RegimeVerdict = {
  plain?: string
  rules?: Record<string, string>
  confirmation?: string
  event_risk?: string
  [k: string]: unknown
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
    verdict?: RegimeVerdict | string | null
    horizon_1m?: HorizonScenario | string | null
    horizon_3m?: HorizonScenario | string | null
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
  // one retry — a flaky 5xx/timeout shouldn't leave a whole section
  // blank; the second attempt bypasses the Data Cache in case the
  // failed response itself was cached
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${BASE}/api/v1/board${path}`, {
        ...(attempt === 0
          ? { next: { revalidate: 120 } }
          : { cache: 'no-store' }),
        signal: AbortSignal.timeout(20_000),
      })
      if (res.ok) return (await res.json()) as T
    } catch {
      // fall through to the retry
    }
    if (attempt === 0)
      await new Promise((r) => setTimeout(r, 400))
  }
  return null
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
  dip_phase?: string
  spring?: number
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

export async function getRaw<T>(
  path: string, opts?: { fresh?: boolean },
): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...(opts?.fresh ? { cache: 'no-store' as const } : { next: { revalidate: 120 } }),
      signal: AbortSignal.timeout(20_000),
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
  passive: () => get<PassiveBoard>('/passive'),
  incomePlan: (funds?: number) =>
    get<IncomePlan>(`/income-plan${funds ? `?funds=${funds}` : ''}`),
  tradePlans: () =>
    get<{ open?: PlanRow[]; closed?: PlanRow[] }>('/trade-plans?all=1'),
  selloff: () => get<SelloffScan>('/selloff'),
  shortSqueeze: (symbol: string) =>
    get<SqueezeEval>(`/short-squeeze/${encodeURIComponent(symbol)}`),
  intraday: () => get<IntradayTape>('/intraday'),
  correctionAlarms: () => get<CorrectionAlarms>('/correction-alarms'),
}

export type CorrectionAlarms = {
  as_of?: string
  correction_character?: string
  severity?: string
  meaning?: string
  action?: { bias?: string; note?: string }
  legs?: {
    revision_breadth?: { score?: number | null; pct_cutting_5?: number; sectors_negative?: string[]; note?: string }
    labor_credit?: { score?: number | null; hy_oas?: number | null; hy_oas_d20?: number | null; icsa_k?: number | null; note?: string }
    real_yields?: { score?: number | null; dfii10?: number | null; dfii10_d20?: number | null; note?: string }
    valuation_decomp?: { score?: number | null; kind?: string; note?: string }
  }
}

export type IntradayTape = {
  state?: string
  ts?: string
  eval?: {
    qqq_chg_open?: number
    above_vwap?: boolean
    vwap_held?: boolean
    vix?: number | null
    vix_rising?: boolean
    vix_falling?: boolean
    leadership?: string | null
    macro_pressure?: boolean
    breadth_adv_pct?: number | null
    breadth_n?: number | null
    morning_recovery?: boolean
    evidence?: string[]
  }
  timeline?: { ts: string; state: string }[]
}

export type SqueezeEval = {
  symbol: string
  verdict?: string
  fuel?: number | null
  covering_probability?: number | null
  data_quality?: string
  rally?: boolean
  ret_5d?: number | null
  rel_vol?: number | null
  si_pct?: number | null
  days_to_cover?: number | null
  si_delta?: number | null
  sv_ratio_latest?: number | null
  sv_trend?: number | null
  evidence?: string[]
  si_series?: { d: string; si: number; pct: number | null; dtc: number | null }[]
  sv_series?: { d: string; ratio: number | null }[]
}

export type SelloffScan = {
  as_of?: string
  note?: string
  market?: {
    active?: boolean
    level?: string
    breadth_score?: number | null
    spy_5d?: number | null
    vix?: number | null
    vxn?: number | null
    reason?: string
  }
  candidates?: SelloffCand[]
}

export type SelloffCand = {
  symbol: string
  name?: string
  sector?: string
  tier?: string
  classification?: string
  action?: string
  score?: number
  legs?: Record<string, number>
  decision?: string
  gates?: string[]
  close?: number
  ret_5d?: number | null
  rel_5d?: number | null
  dd_60d?: number | null
  vol_ratio?: number | null
  rsi?: number | null
  mom?: string
  sq_verdict?: string | null
  sq_fuel?: number | null
  sq_covering_prob?: number | null
  fund_state?: string
  thesis?: string | null
  fv?: number | null
  fv_upside?: number | null
  invalidation?: number | null
  earn_days?: number | null
  entry_plan?: {
    stages?: { pct: number; trigger: string }[]
    invalidation?: number | null
    invalidation_note?: string
  }
}

export type IncomePlan = {
  as_of?: string
  posture?: {
    posture?: string
    new_longs?: boolean
    note?: string
    matched?: string
    regime_as_of?: string
  }
  funds?: number | null
  bias?: string
  bias_note?: string
  note?: string
  lanes?: {
    swing?: PlanSuggestion[]
    leap_call?: PlanSuggestion[]
    leap_put?: PlanSuggestion[]
    csp?: PlanSuggestion[]
    covered_call?: PlanSuggestion[]
  }
  sectors?: {
    sector: string
    lanes: {
      swing?: PlanSuggestion[]
      leap_call?: PlanSuggestion[]
      leap_put?: PlanSuggestion[]
      csp?: PlanSuggestion[]
      covered_call?: PlanSuggestion[]
    }
  }[]
}

export type PlanSuggestion = {
  symbol: string
  name?: string
  sector?: string
  instrument?: string
  use_case?: string
  intent?: string
  top?: boolean
  pick_score?: number
  exit_rule?: string
  score?: number
  rank?: number
  lane_state?: string
  entry_px?: number
  spot?: number
  stop_px?: number
  target_px?: number
  rr?: number
  strike?: number
  collateral?: number
  contracts?: number
  shares?: number
  dte?: string
  iv_hv?: number
  state?: string
  dip_phase?: string
  mom?: string
  fund?: string
  thesis?: string
  thesis_dir?: string
  earn_days?: number
  flags?: string[]
  evidence?: string[]
  plan?: Record<string, unknown>
}

export type PlanRow = {
  id: number
  symbol: string
  use_case?: string
  direction?: string
  entry_px?: number
  entry_date?: string
  stop_px?: number
  target1_px?: number
  target2_px?: number
  thesis?: string
  status?: string
  last_status?: string
  px?: number
  r?: number
  days?: number
  dist_stop?: number
  eval?: { status?: string; action_hint?: string; why?: string }
}

export type PassiveBoard = {
  as_of?: string
  posture?: string
  matched?: string
  verdict?: {
    action?: string
    tone?: string
    headline?: string
    note?: string
    flipped?: boolean
  }
  book?: {
    name?: string
    base?: Record<string, number>
    tilt?: Record<string, number>
    reason?: string
    note?: string
  }
  context?: {
    spy_vs_200?: number
    lead_scenario?: string
    dip_character?: string
    p_deeper_dip?: number
    verdict_line?: string
  }
  tilt_history?: { as_of?: string; posture?: string; tilt?: Record<string, number>; reason?: string }[]
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
