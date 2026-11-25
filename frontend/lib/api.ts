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

export type RecoveryVerdict = {
  symbol?: string; as_of?: string; state?: string; prev_state?: string
  state_changed?: boolean; transition_reason?: string
  event_type?: string; market?: Record<string, unknown>
  stock?: Record<string, unknown>; recovery?: Record<string, unknown>
  decision?: string; decision_confidence?: string
  gates?: Record<string, boolean>; conflicts?: Array<Record<string, unknown>>
  required_confirmation?: string[]; invalidation_conditions?: string[]
  evidence_refs?: Array<Record<string, unknown>>; missing_inputs?: string[]
}

export type ThesisChangeEvent = {
  id?: number
  symbol?: string
  as_of?: string
  event_kind?: 'coverage_start' | 'status_transition' | 'leg_change'
  archetype?: string
  prev_status?: string | null
  status?: string
  status_dir?: string
  score?: number
  hyp_changes?: { id?: string; archetype?: string; from?: string; to?: string }[]
  veto_fired?: { id?: string; flag?: string; cap?: string; fatal?: boolean }[] | null
  evidence?: {
    hypothesis_id?: string
    archetype?: string
    status?: string
    label?: string
    checks?: { metric?: string; status?: string; note?: string; hard?: boolean }[]
  }[]
  drivers?: Record<string, unknown>[]
  fv_delta_pct?: number | null
  priced_in?: string | null
  alert_id?: string | null
  detail?: Record<string, unknown>
  created_at?: string
}

export type IntradayRegime = {
  as_of?: string
  session_date?: string
  market_time?: string
  baseline_as_of?: string
  baseline_regime?: string
  baseline_score?: number
  tape_state?: string
  tape_ts?: string
  stale?: boolean
  age_minutes?: number
  state?: string
  action?: string
  tone?: string
  evidence?: Record<string, unknown>
}

export type Fragility = {
  as_of?: string
  vulnerability?: number | null
  band?: string
  selling_pressure?: {
    score?: number | null
    band?: string
    status?: string
    read?: string
  } | null
  probabilities?: Record<string, Record<string, number>>
  prob_model?: string
  confidence?: string
  coverage_pct?: number | null
  data_quality?: {
    completeness_pct?: number | null
    estimated_pct?: number | null
    missing?: string[]
    confidence?: string
  }
  firing?: string[]
  legs?: Record<string, {
    score?: number | null
    status?: string
    read?: string
    trigger_state?: string
    breached?: string[]
    nearest_unbroken_pct?: number | null
    signals?: Record<string, unknown>
  }>
  exhaustion?: {
    score?: number | null
    band?: string
    status?: string
    read?: string
    legs?: Record<string, { score?: number | null; status?: string;
                            read?: string }>
  } | null
  validators?: Record<string, unknown>
  resolution?: {
    phase?: string
    discharge_score?: number | null
    bottom_score?: number | null
    read?: string
  }
  sectors?: Array<{
    etf?: string; label?: string
    score?: number | null; band?: string | null
    score_delta?: number | null
    legs?: Record<string, Record<string, unknown>>
    missing?: string[]
  }>
  leverage_cycle?: {
    phase?: string
    what_to_do?: string
    basis?: Record<string, boolean | null>
    discharge_score?: number | null
    exhaustion_score?: number | null
  } | null
  missing?: string[]
  read?: string
  computed_at?: string
}

export type MorningRegime = {
  today?: {
    as_of?: string
    regime?: string
    ai_regime?: string
    score?: number
    // engine journals a band ('low'|'medium'|'high'); older snapshots
    // used a numeric pct — accept both
    confidence?: number | string
    buckets?: Record<string, unknown> | unknown[]
    llm?: unknown
    verdict?: RegimeVerdict | string | null
    horizon_1m?: HorizonScenario | string | null
    horizon_3m?: HorizonScenario | string | null
  } | null
  intraday?: IntradayRegime | null
  fragility?: Fragility | null
  movement?: {
    regime_clock?: {
      regime?: string; since?: string; days?: number; prev?: string | null
    } | null
    flips?: Array<{ as_of?: string; from?: string; to?: string }>
    sectors?: Array<{
      symbol?: string; ret1?: number | null
      ret5?: number | null; ret20?: number | null
      vs_spy1?: number | null
      vs_spy5?: number | null; vs_spy20?: number | null
    }>
    smh_ew?: {
      as_of?: string; risk?: number | null; state?: string | null
      destinations?: string[]
    } | null
  } | null
  valuation?: {
    as_of?: string
    spy_pe_trailing?: number | null
    qqq_pe_trailing?: number | null
    tracked_fwd_pe?: number | null
    tracked_names?: number | null
    tracked_cap_usd?: number | null
    tracked_ey_pct?: number | null
    tnx_yield_pct?: number | null
    tnx_as_of?: string | null
    ey_spread_pp?: number | null
    spread_change_1w_bps?: number | null
    spread_change_1m_bps?: number | null
    eps_rev_n?: number | null
    eps_rev_up_n?: number | null
    eps_rev_down_n?: number | null
    eps_rev_flat_n?: number | null
    eps_rev_breadth?: number | null
    fwd_eps_growth_fy1_fy2?: number | null
    fwd_eps_growth_n?: number | null
    earnings_verdict?: string | null
    earnings_tone?: 'ok' | 'warn' | 'bad' | null
    earnings_headline?: string | null
    earnings_detail?: string | null
    stance?: string | null
    stance_label?: string | null
    stance_tone?: 'ok' | 'warn' | 'bad' | null
    stance_headline?: string | null
    stance_detail?: string | null
    verdict?: string | null
    verdict_tone?: 'ok' | 'warn' | 'bad' | null
    headline?: string | null
    detail?: string | null
    obs_n?: number | null
    spy_pe_pctile?: number | null
    ey_spread_pctile?: number | null
  } | null
  posture?: {
    posture?: string | null
    posture_label?: string | null
    posture_tone?: 'ok' | 'warn' | 'bad' | null
    posture_headline?: string | null
    posture_detail?: string | null
  } | null
  rates?: {
    rates_direction?: 'cooling' | 'reheating' | 'flat' | null
    rates_tone?: 'ok' | 'warn' | 'bad' | null
    rates_headline?: string | null
    rates_detail?: string | null
    nf_as_of?: string | null
    realtime_yoy?: number | null
    realtime_wow_pp?: number | null
    rt_d7_pp?: number | null
    rt_d30_pp?: number | null
    spark?: string | null
    drivers?: Array<{
      key?: string; label?: string; yoy?: number
      contribution?: number; state?: string; status?: string
    }> | null
    official_yoy?: number | null
    official_month?: string | null
    print_forecast_yoy?: number | null
    wti_value?: number | null
    wti_chg5d?: number | null
    fed_lean?: string | null
    fed_expected_bps?: number | null
    fomc_date?: string | null
    fomc_days?: number | null
    p_hike?: number | null
    p_hold?: number | null
    p_cut?: number | null
    p_hike_d7?: number | null
    bps_d7?: number | null
    compare_to?: string | null
  } | null
  direction?: {
    direction?: string | null
    direction_label?: string | null
    direction_tone?: 'ok' | 'warn' | 'bad' | null
    direction_headline?: string | null
    direction_detail?: string | null
  } | null
  outlook?: {
    next_day?: { verdict?: string | null; score?: number | null
                 tone?: string; evidence?: string[] } | null
    weeks?: { verdict?: string | null; score?: number | null
              tone?: string; evidence?: string[] } | null
    months?: { verdict?: string | null; score?: number | null
               tone?: string; evidence?: string[] } | null
  } | null
  record?: Array<Record<string, unknown>>
}

export type MetalCard = {
  class?: string
  opportunity?: number | null
  fundamental?: number | null
  fear?: number | null
  verdict?: string
  price?: number | null
  hi_52w?: number | null
  lo_52w?: number | null
  off_52w_high_pct?: number | null
  rsi14?: number | null
  ret20?: number | null
  ret60?: number | null
  falling_knife?: boolean
  stabilized?: boolean | null
  reason?: string
  legs?: {
    fundamental?: { name?: string; score?: number; weight?: number; value?: string }[]
    fear?: { name?: string; score?: number; weight?: number; value?: string }[]
  }
  thesis?: string
  recovery_drivers?: string[]
  invalidates_when?: string
  missing?: string[]
  stage2_pending?: string[]
  price_as_of?: string
}

export type MetalsPulse = {
  today?: {
    as_of?: string
    age_days?: number
    macro?: {
      label?: string
      crypto_label?: string
      drivers?: string[]
      components?: Record<string, unknown>
    }
    gs_ratio_pctile?: number | null
    metals?: Record<string, MetalCard>
    crypto?: Record<string, MetalCard>
    transitions?: {
      as_of_prev?: string | null
      macro_prev?: string | null
      macro_now?: string | null
      macro_flipped?: boolean
      crypto_label_prev?: string | null
      crypto_label_now?: string | null
      crypto_label_flipped?: boolean
      first_run?: boolean
      assets?: Record<string, {
        verdict_prev?: string | null
        verdict_now?: string | null
        newly_actionable?: boolean
        fundamental_delta?: number | null
      }>
    }
  } | null
}

export type ThemeCard = {
  name?: string
  stage?: string
  thesis?: string
  opportunity?: number | null
  verdict?: string
  expected?: number
  downside?: number
  robustness?: number
  dispersion?: number
  legs?: { name?: string; score?: number; weight?: number; value?: string }[]
  missing?: string[]
  index?: {
    pure_n?: number
    quality_n?: number
    ineligible?: string[]
    weights?: Record<string, number>
    top?: {
      symbol?: string
      weight?: number
      score?: number
      role?: string
      stance?: string | null
      advice?: string
      reason?: string
    }[]
  }
  pool?: {
    symbol?: string
    exposure?: string
    score?: number | null
    note?: string
    stance?: string | null
    stance_reason?: {
      meaning?: string | null
      because?: string[]
      gaps?: string[]
    } | null
    business_strength?: number | null
    fv_upside_pct?: number | null
    est_revision_pct?: number | null
  }[]
  _weights?: {
    pure?: { weights?: Record<string, number>; n?: number }
    quality?: { weights?: Record<string, number>; scores?: Record<string, number>; n?: number }
  }
}

export type ThemeIntelligence = {
  today?: {
    as_of?: string
    age_days?: number
    scenario_probs?: Record<string, number>
    themes?: Record<string, ThemeCard>
  } | null
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

async function get<T>(path: string, opts?: { fresh?: boolean }): Promise<T | null> {
  // one retry — a flaky 5xx/timeout shouldn't leave a whole section
  // blank; the second attempt bypasses the Data Cache in case the
  // failed response itself was cached. `fresh` bypasses it on the
  // first attempt too — for live signals (the tape) staleness is
  // worse than a cache hit
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${BASE}/api/v1/board${path}`, {
        ...(attempt === 0 && !opts?.fresh
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

export type EarningsCapture = {
  symbol: string
  earnings_date: string
  verdict: string
  surprise_pct?: number | null
  thesis_before?: string | null
  thesis_after?: string | null
  detail?: Record<string, unknown>
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
  prev_close?: number | null
  day_chg_pct?: number | null
  spark?: number[] | null
  mom_state?: string
  mom_prev?: string
  dip_phase?: string
  spring?: number
  stoch_w_up?: boolean | null
  stoch_w_zone?: string | null
  stoch_d_cross?: string | null
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
  day_pnl?: number
  day_chg_pct?: number | null
  target_pct?: number
  on_pace?: boolean
  track_days?: number
  track_ret_pct?: number
  track_target_pct?: number
  spy_ret_pct?: number
  excess_pct?: number
  goal_month?: number
}

export type EarningsHighlight = {
  metric?: string
  actual?: number | string | null
  consensus?: number | string | null
  delta_pct?: number | null
  yoy_pct?: number | null
  unit?: string
  note?: string | null
}

export type EarningsReport = {
  symbol?: string
  earnings_date?: string
  version?: number
  title?: string
  generated_by?: string
  created_at?: string
  report?: {
    symbol?: string
    earnings_date?: string
    quarter_label?: string
    company_name?: string
    sector?: string
    market_cap_b?: number | null
    rating?: string | null
    headline?: string
    verdict?: string
    print?: {
      eps_estimate?: number | null
      eps_actual?: number | null
      adjusted_eps_actual?: number | null
      surprise_pct?: number | null
      revenue_estimate_b?: number | null
      revenue_actual_b?: number | null
      rev_surprise_pct?: number | null
      one_time?: Record<string, unknown> | null
    }
    highlights?: EarningsHighlight[]
    growth?: {
      quarter_yoy?: number | null
      two_year_ann?: number | null
      five_year_cagr?: number | null
      forward_12m?: number | null
      quarters_tracked?: number
    } | null
    quality?: {
      operating_margin?: number | null
      operating_margin_yoy_pp?: number | null
      fcf_margin?: number | null
      fcf_margin_yoy_pp?: number | null
      net_margin?: number | null
      gross_margin?: number | null
      beat_streak?: number | null
      avg_surprise_pct?: number | null
    } | null
    expectations?: {
      fwd_eps_avg?: number | null
      fwd_rev_avg_b?: number | null
      fwd_pe?: number | null
      num_analysts?: number | null
      est_revision_pct?: number | null
      gap_score?: number | null
      muted_reaction?: boolean | null
      stance_reason?: {
        meaning?: string
        because?: string
        gaps?: string
      } | null
    } | null
    guidance_drivers?: Array<Record<string, unknown>>
    thesis?: { before?: string | null; after?: string | null }
    narrative?: string | null
    takeaways?: string[]
    bull_bear?: { bull?: string[]; bear?: string[];
                  bull_summary?: string; bear_summary?: string }
    prior_prints?: Array<{
      earnings_date?: string
      eps_estimate?: number | null
      eps_actual?: number | null
      revenue_actual?: number | null
      surprise_percentage?: number | null
      verdict?: string | null
      report_version?: number | null
    }>
    version?: number
  }
}

export type EarningsReportVersion = {
  earnings_date?: string
  version?: number
  title?: string
  generated_by?: string
  created_at?: string
}

export type EarningsReportFeedRow = {
  symbol?: string
  earnings_date?: string
  version?: number
  title?: string
  verdict?: string
  created_at?: string
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

export interface ForwardOutlook {
  market?: {
    as_of?: string
    current_state?: Record<string, number>
    analogs?: { date: string; distance: number }[]
    horizons?: Record<string, {
      n?: number; median_pct?: number; p25_pct?: number
      p75_pct?: number; pct_positive?: number; worst_pct?: number
      low_evidence?: boolean }>
    error?: string
  }
  event_study?: {
    events_n?: number; symbols?: number
    by_verdict?: Record<string, Record<string, {
      n?: number; median_pct?: number; pct_positive?: number
      low_evidence?: boolean }>>
  }
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
  forwardOutlook: (sym?: string) =>
    get<ForwardOutlook>(
      `/forward-outlook${sym ? `?sym=${sym}` : ''}`),
  posture: () => get<Posture>('/posture'),
  morningRegime: () => get<MorningRegime>('/morning-regime'),
  metalsPulse: () => get<MetalsPulse>('/metals-pulse'),
  themeIntelligence: () =>
    get<ThemeIntelligence>('/theme-intelligence'),
  sectorTiming: () =>
    get<{ sectors?: Array<Record<string, unknown>>;
          history_days?: number }>('/sector-timing'),
  macroEvents: () =>
    get<{ events?: MacroEvent[] } | MacroEvent[]>('/macro-events'),
  daily: () => get<DailyBoard>('/daily'),
  receipts: (limit = 100) =>
    get<{ decisions?: Receipt[]; regime?: RegimeReceipt[] }>(
      `/receipts?limit=${limit}`,
    ),
  portfolioPulse: (portfolioId?: string) =>
    get<{ as_of?: string; rows?: PulseRow[]; book?: PulseBook }>(
      `/portfolio-pulse${portfolioId
        ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : ''}`,
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
  recoveryVerdict: (sym: string) =>
    get<{ symbol: string; latest?: RecoveryVerdict | null; history?: RecoveryVerdict[] }>(
      `/symbol/${encodeURIComponent(sym.toUpperCase())}/recovery-verdict`),
  thesisHistory: (sym: string, days = 180) =>
    get<{ symbol?: string; events?: ThesisChangeEvent[] }>(
      `/symbol/${encodeURIComponent(sym)}/thesis-history?days=${days}`,
    ),
  pricedIn: (sym: string) =>
    get<{ symbol?: string; latest?: Record<string, unknown> | null;
          history?: Array<Record<string, unknown>> }>(
      `/symbol/${encodeURIComponent(sym.toUpperCase())}/priced-in`),
  valuationDecision: (sym: string) =>
    get<{ symbol?: string; latest?: Record<string, unknown> | null;
          history?: Array<Record<string, unknown>> }>(
      `/symbol/${encodeURIComponent(sym.toUpperCase())}/valuation-decision`),
  earningsCalendar: (start: string, end: string) =>
    getRaw<{ success?: boolean; count?: number; data?: EarningsRow[] }>(
      `/admin/earnings-calendar?start_date=${start}&end_date=${end}`,
    ),
  earningsWatch: (days = 30) =>
    get<{ reporters?: string[]; captures?: EarningsCapture[] }>(
      `/earnings-watch?days=${days}`,
    ),
  earningsReport: (sym: string, date?: string, version?: number) =>
    get<EarningsReport>(
      `/earnings-report/${sym}` +
      (date ? `?date=${date}${version ? `&version=${version}` : ''}`
            : version ? `?version=${version}` : ''),
    ),
  earningsReportVersions: (sym: string) =>
    get<{ symbol?: string; versions?: EarningsReportVersion[] }>(
      `/earnings-report/${sym}/versions`,
    ),
  earningsReportsFeed: (days = 30) =>
    get<{ reports?: EarningsReportFeedRow[] }>(
      `/earnings-reports?days=${days}`,
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
    get<{
      open?: PlanRow[]; closed?: PlanRow[];
      outcomes?: PlanOutcomeStats
    }>('/trade-plans?all=1'),
  selloff: () => get<SelloffScan>('/selloff'),
  bestPicks: () => get<BestPicks>('/best-picks'),
  levSwings: (funds?: number) =>
    get<LevSwings>(`/leveraged-swings${funds ? `?funds=${funds}` : ''}`),
  shortSqueeze: (symbol: string) =>
    get<SqueezeEval>(`/short-squeeze/${encodeURIComponent(symbol)}`),
  intraday: () => get<IntradayTape>('/intraday', { fresh: true }),
  fragility: () => get<Fragility>('/fragility'),
  resilience: (symbol: string) => get<ResilienceCard>(`/resilience/${symbol}`),
  readinessStates: () => get<{ as_of: string | null; use_cases: Record<string, Record<string, { symbol: string; score: number | null; rank: number | null }[]>> }>('/readiness-states'),
  intradayRecovery: () => get<{
    as_of?: string | null; stale?: boolean | null;
    participation?: number | null;
    symbols?: { symbol: string; signal: string; score?: number | null;
                bar_ts?: string; vwap_hold_min?: number | null;
                rs30_smh?: number | null; rvol?: number | null;
                delta_vol?: number | null;
                recovery_score?: number | null;
                accumulation_score?: number | null;
                overextended?: boolean | null;
                vwap?: number | null; last?: number | null;
                ext_pct?: number | null }[]
  }>('/intraday-recovery'),
  intradayRecoverySession: (symbol: string) => get<{
    symbol?: string; as_of?: string;
    gap_pct?: number | null; prev_close?: number | null;
    bars?: { ts: string; o?: number | null; h?: number | null;
             l?: number | null; c?: number | null;
             v?: number | null }[];
    vwap?: number[]; smh?: number[];
    evals?: { ts: string; signal: string; score?: number | null;
              rec?: number | null; accum?: number | null;
              dvol?: number | null; rvol?: number | null;
              hold_min?: number | null }[];
    transitions?: { ts: string; from: string; to: string }[];
  }>(`/intraday-recovery/${encodeURIComponent(symbol)}/session`),
  cycle: () => get<{
    as_of?: string | null; quarter_label?: string | null; n?: number;
    rows?: CycleRow[];
    cohorts?: Record<string, {
      n: number; scored: number; median?: number | null;
      decisions?: Record<string, number>; label?: string;
      phase?: string | null;
      peak?: { lo?: number; hi?: number; confidence?: string } | null
    }>
  }>('/cycle'),
  aiCycleLadder: () => get<{
    as_of?: string;
    regime?: { regime?: string;
               groups?: Record<string, string>;
               up_groups?: string[];
               down_groups?: string[] };
    warning?: { score?: number; down_groups?: number };
    rungs?: Record<string, {
      stage?: string; description?: string; members?: string[];
      tape?: { rel_5d?: number; rel_20d?: number };
      growth?: { med_weighted_growth?: number;
                 med_peg_cagr?: number; n_growth?: number };
      evidence?: { n_claims?: number; axes_up?: number;
                   axes_down?: number;
                   axes?: Record<string, {
                     value?: string | null; direction?: string;
                     confidence?: string; n?: number }> };
      profile?: { models?: Record<string, number>;
                  monetization?: Record<string, number>;
                  funding_worst?: string };
      rotation_state?: string;
    }>
  }>('/ai-cycle-ladder'),
  transitions: () => get<{
    readiness?: { symbol: string; use_case: string;
                  prev_state?: string; state?: string;
                  score?: number; of?: number;
                  prev_as_of?: string; as_of?: string }[]
    pulse?: { symbol: string; prev_action?: string; action?: string;
              label?: string | null; matched_rule?: string | null;
              prev_as_of?: string; as_of?: string }[]
  }>('/transitions'),
  guidanceAll: () => get<{ items: { symbol: string; outlook: number | null; quality: number | null }[] }>('/guidance'),
  guidance: (symbol: string) => get<GuidanceCard>(`/guidance/${symbol}`),
  resilienceAll: () => get<{ items: ResilienceRow[] }>('/resilience'),
  readiness: () => get<ReadinessBoard>('/readiness'),
  correctionAlarms: () => get<CorrectionAlarms>('/correction-alarms'),
  researchBoard: (sector = 'healthcare') =>
    getRaw<{
      success?: boolean; sector?: string; rows?: ResearchRow[];
      llm_tier?: string
    }>(
      `/admin/research/board?sector=${encodeURIComponent(sector)}`,
    ),
  researchReport: (sym: string) =>
    getRaw<{
      success?: boolean
      run?: ResearchRun | null
      delta?: ResearchDelta | null
      growth?: GrowthUplift | null
    }>(`/admin/research/${encodeURIComponent(sym)}`),
}

export type CycleRow = {
  symbol: string
  quarter_label?: string
  as_of?: string
  cohort?: string | null
  composite?: number | null
  coverage_pct?: number | null
  demand_accel?: number | null
  backlog_quality?: number | null
  est_revisions?: number | null
  margin_cf?: number | null
  capacity_util?: number | null
  customer_adoption?: number | null
  capital_recovery?: number | null
  valuation_duration?: number | null
  order_peak?: boolean | null
  estimate_peak?: boolean | null
  revenue_peak?: boolean | null
  demand_peak_lo?: number | null
  demand_peak_hi?: number | null
  peak_confidence?: string | null
  peak_source?: string | null
  peak_movement?: string | null
  quarters_to_peak?: number | null
  rev_peak_risk?: number | null
  decision?: string | null
  structural_break?: boolean | null
  valuation_blocked?: boolean | null
  flags?: string[]
  g27?: number | null
  g28?: number | null
  rev_cagr?: number | null
  eps_g28?: number | null
  eps_cagr?: number | null
  peg?: number | null
  est_mom?: number | null
  est_mom60?: number | null
  rev_mom?: number | null
  analysts?: number | null
  disp?: number | null
  coverage_shift?: number | null
  rank_growth?: number | null
  rank_gq?: number | null
  rank_gap?: number | null
  req_cagr?: number | null
  exp_gap?: number | null
  implied_status?: string | null
  exposure?: string | null
  eps_g27?: number | null
  selloff_class?: string | null
  selloff_decision?: string | null
  sbd_class?: string | null
  pf_gap?: number | null
  business_bucket?: string | null
  selloff_as_of?: string | null
  gq?: number | null
  gq_delta?: number | null
  est_rel?: string | null
  cvd?: number | null
  cyclical_flag?: boolean | null
  recovery_year?: boolean | null
  growth_as_of?: string | null
  crs?: number | null
  risk_trend?: string | null
  displacement_confirmed?: boolean | null
  opportunity_credit?: number | null
  ais?: number | null
  agentic_tier?: string | null
  sublayers?: string[]
  monetization?: string | null
  top_threats?: {
    competitor?: string; segment?: string; type?: string;
    stage?: string; share?: (number | null)[];
    probability?: number | null; claim?: string;
    source?: string; source_date?: string | null
  }[]
  components?: Record<string, {
    score?: number | null; weight?: number;
    note?: string | null; unknown?: boolean
  }> | null
  decision_detail?: {
    note?: string | null
    conditions?: Record<string, string>
    missing?: string[]
  } | null
}

export type CycleHistoryRow = {
  quarter_label?: string
  as_of?: string
  composite?: number | null
  coverage_pct?: number | null
  decision?: string | null
  rev_peak_risk?: number | null
  demand_peak_lo?: number | null
  demand_peak_hi?: number | null
  peak_movement?: string | null
  quarters_to_peak?: number | null
  order_peak?: boolean | null
  estimate_peak?: boolean | null
  revenue_peak?: boolean | null
  flags?: string[]
  decision_detail?: { note?: string | null;
                      conditions?: Record<string, string> } | null
}

export type ResearchRow = {
  symbol: string
  name?: string | null
  industry?: string | null
  business_model?: string | null
  ai_tailwind?: number | null
  business_strength?: number | null
  recommendation?: string | null
  best_product?: { name?: string; stage?: string; moats?: string[] } | null
  product_score?: number
  fdcs?: number | null
  ecs?: number | null
  transition_net?: string | null
  horizon?: string | null
  as_of?: string | null
}

export type ResearchDelta = {
  prev_as_of?: string
  score_diffs?: Record<string, number>
  new_products?: string[]
  new_wins?: string[]
  rec_change?: { from?: string; to?: string } | null
  news_scan?: {
    fetched?: number; analyzed?: number; claims?: number
    skipped_seen?: number; skipped_noise?: number
    skipped_stale?: number
  } | null
}

export type GrowthUplift = {
  uplift_fy1?: number | null
  uplift_fy3?: number | null
  uplift_ratio_fy3?: number | null
  tier?: string | null
  n_initiatives?: number
  fwd_rev_avg?: number | null
}

export type ResearchRun = {
  as_of?: string
  business_model?: string | null
  ai_tailwind_score?: number | null
  business_strength?: number | null
  recommendation?: string | null
  rules_version?: string | null
  scores?: {
    tailwind?: {
      score?: number
      coverage?: number
      capped?: string | null
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    strength?: {
      score?: number
      coverage?: number
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    quality?: {
      score?: number
      coverage?: number
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    ai_infra_architecture?: {
      score?: number
      coverage?: number
      capped?: string | null
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    future_demand_capture?: {
      score?: number
      coverage?: number
      capped?: string | null
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    valuation_opportunity?: {
      score?: number
      coverage?: number
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
    technical_entry?: {
      score?: number
      coverage?: number
      components?: Record<string, { score?: number | null; weight?: number; note?: string | null; unknown?: boolean }>
    }
  }
  report?: {
    sector?: string
    products?: { name?: string; stage?: string; moat?: string[]; layer?: string | null; why?: string }[]
    design_wins?: { customer?: string; product?: string; stage?: string; revenue_confirmed?: boolean }[]
    fdce?: {
      domain_exposure?: Record<string, { weight?: number; products?: string[]; horizon?: string; d_score?: number }>
      ecs?: { ecs?: number | null; highest_evidence_stage?: string; production_exposure_pct?: number | null; roadmap_exposure_pct?: number | null }
      transitions?: { net?: string; adjusted_delta?: number; items?: { transition?: string; product?: string; classification?: string }[] }
      adjusted_fdcs?: number | null
      horizon?: { dominant_domain?: string; dominant_horizon?: string }
      rules_version?: string
    } | null
    challenge?: { question?: string; finding?: string; severity?: string }[]
    hard_gates?: string[]
    evidence_coverage?: number | null
    evidence_state?: string | null
    llm_tier?: string | null
    recommendation?: {
      action?: string; note?: string | null; flags?: string[]
      reason?: {
        meaning?: string | null
        because?: string[]
        flags?: string[]
        gaps?: string[]
        closest?: { action?: string; needs?: string[] } | null
      }
    }
    quarters?: {
      period_end?: string
      filing_date?: string | null
      revenue?: { value?: number | null }
      gross_margin?: { value?: number | null }
      op_margin?: { value?: number | null }
      net_income?: { value?: number | null }
      free_cf?: { value?: number | null }
      cash?: { value?: number | null }
      total_debt?: { value?: number | null }
      shares_diluted?: { value?: number | null }
    }[]
  }
}

export type ReadinessRow = {
  symbol: string
  name?: string | null
  state?: string            // ready | close | no
  score?: number | null
  of?: number | null
  fails?: string[] | null
  rank?: number | null
  parts?: Record<string, unknown> | null
  mom?: string | null
  fund?: string | null
  thesis?: string | null
  thesis_dir?: string | null
  fv_upside?: number | null
  mcap_b?: number | null
  catalyst?: string | null
  swing_phase?: string | null
  confirm_level?: number | null
  avwap?: number | null
  prior_low?: number | null
  dip_phase?: string | null
  stab?: number | null
  vol_dip?: number | null
  pe_band?: string | null
  pe_cat?: string | null
  stage_txt?: string | null
}

export type ReadinessBoard = {
  as_of?: string | null
  sections?: Record<string, ReadinessRow[]>
  skipped?: string[]
  counts?: Record<string, { ready?: number; close?: number; no?: number }>
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
  base_rate?: {
    state?: string
    n?: number
    day_median?: number | null
    day_red_pct?: number | null
    next_median?: number | null
    next_red_pct?: number | null
  } | null
  open_base_rate?: {
    state?: string
    n?: number
    day_median?: number | null
    day_red_pct?: number | null
    next_median?: number | null
    next_red_pct?: number | null
  } | null
  premarket?: {
    slots?: Array<{
      slot?: string; ts?: string
      qqq_gap?: number | null; spy_gap?: number | null
      smh_gap?: number | null
      btc_chg?: number | null; eth_chg?: number | null
    }>
  } | null
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
    levels?: Record<string, {
      close?: number; vwap?: number; dist_pct?: number
      day_ret_pct?: number; reclaim?: number; confirm?: number
      support?: number; warning?: number; above?: boolean
    }>
  }
  timeline?: {
    ts: string
    state: string
    qqq_chg_open?: number | null
    spy_chg_open?: number | null
    above_vwap?: boolean | null
    vwap_held?: boolean | null
    vix?: number | null
    vix_rising?: boolean | null
    vix_falling?: boolean | null
    breadth_adv_pct?: number | null
    leadership?: string | null
    macro_pressure?: boolean | null
    smh_above_vwap?: boolean | null
    smh_vwap_held?: boolean | null
    evidence?: string[] | null
  }[]
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
  dimensions?: {
    business_health?: number | null
    stock_dislocation?: number | null
    valuation_attractiveness?: number | null
    recovery_confirmation?: number | null
  }
  business_bucket?: string
  bucket_notes?: string[]
  pf_gap?: number | null
  pf_gap_note?: string | null
  sbd?: { class?: string; action?: string }
  sbd_rank?: number
  confidence?: string
  decline_cause?: string
  technical_flags?: string[]
  reason?: string
  growth_quality?: number | null
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

export type BestPicks = {
  as_of?: string
  rules_version?: string
  evaluated?: number
  sections?: Record<string, BestPickSection>
}

export type BestPickSection = {
  horizon?: string
  picks?: BestPick[]
  watch?: BestPick[]
  counts?: { picks?: number; watch?: number; excluded?: number }
}

export type LevSwings = {
  as_of?: string
  signal_src?: string
  funds?: number | null
  risk_pct?: number
  caveat?: string
  error?: string
  rules_version?: string
  exit?: {
    max_hold_bars?: number; time_stop?: string
    targets?: { r: number; close: number }[]
  }
  etfs?: Record<string, LevEtf>
}

export type LevEtf = {
  state: string                 // flat | armed | triggered | vetoed
  armed?: boolean
  actionable?: boolean          // triggered + data + priceable stop
  veto?: string | null
  warn?: string | null
  state_note?: string | null    // rejection/cap notes
  data_missing?: string[]
  persisting?: boolean          // same state as prior journal day
  missing?: string[]
  hold?: {                      // sell-timing read for a holder
    verdict: string             // exit | take profits | hold | watch
    why?: { role: string; line: string }[]
    days?: number
    time_stop?: string
  }
  position?: {                  // open system/paper position
    entry?: number | null
    px?: number | null
    unrealized_r?: number | null
    stop?: number | null
    partials?: number
    bars_held?: number
    banked_r?: number
    realized_r?: number | null
    exit_reason?: string | null
    state?: string              // open | closed
  }
  checklist?: { ok: boolean; line: string; soft?: boolean }[]
  index?: {
    close?: number; rsi?: number | null; vs50?: number
    ema8?: number; soxx_close?: number | null
  }
  levels?: {
    entry?: number | null; stop?: number | null
    t1?: number | null; t2?: number | null
    t1_frac?: number; t2_frac?: number
    risk_px?: number | null; shares?: number | null
    notional_capped?: boolean
    risk_usd?: number | null; idx_stop?: number
    idx_move?: number; implied_loss_pct?: number
    geometry_invalid?: boolean
  }
  leaders?: {
    tracked?: number; coverage?: number; constructive?: string[]
    hostile?: string[]; ratio?: number | null
  }
}

export type BestPick = {
  symbol: string
  name?: string
  sector?: string
  px?: number | null
  mcap_b?: number | null
  score?: number | null
  tier?: string
  label?: string
  routing?: string[]
  reason?: string
  pillars?: Record<string, number>
  fv?: number | null
  fv_reliability?: string
  mom?: string
  fund?: string
  thesis?: string | null
  selloff?: string | null
  missing?: string[]
}

export type IncomePlan = {
  as_of?: string
  posture?: {
    posture?: string
    new_longs?: boolean
    note?: string
    matched?: string
    regime_as_of?: string
    flags?: string[]
    credit_note?: string
    entry_confirm_required?: boolean
    evidence?: Record<string, unknown>
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
  close_px?: number
  closed_at?: string
  close_reason?: string
  eval?: { status?: string; action_hint?: string; why?: string }
}

export type PlanOutcomeBucket = {
  use_case?: string
  entry_pulse_action?: string
  rules_version?: string
  n?: number
  win_rate?: number
  avg_r?: number
  avg_pct?: number
  avg_days?: number
  t1_rate?: number
  t2_rate?: number
  stop_rate?: number
  invalidated_rate?: number
}

export type PlanOutcomeStats = {
  n?: number
  by_use_case?: PlanOutcomeBucket[]
  by_entry_pulse?: PlanOutcomeBucket[]
  by_rules_version?: PlanOutcomeBucket[]
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

export interface ResilienceCheck {
  label: string; ok: boolean; detail: string; wt?: number; invalid?: boolean
}
export interface ResilienceRow {
  symbol: string; as_of: string
  scores: Record<string, number | null> | null
  delta?: Record<string, number> | null
  prev_as_of?: string | null
  flow?: { footprint?: string | null; streak?: number | null } | null
  tape_live?: { tape_live?: number; rel1?: number; rel5?: number;
                rel20?: number; as_of?: string } | null
  swing_live?: { dip_phase_live?: string; stab_live?: number;
                 stab_cls_live?: string; dip_health_live?: number;
                 as_of?: string } | null
  recovery?: { signal?: string; score?: number | null;
               bar_ts?: string; vwap_hold_min?: number | null;
               rs30_smh?: number | null; rvol?: number | null;
               delta_vol?: number | null;
               recovery_score?: number | null;
               accumulation_score?: number | null;
               overextended?: boolean | null } | null
  flags?: string[]; needs?: string[]
  business_model?: string | null
  themes?: { theme: string; exposure: string }[]
}
export interface ResilienceCard {
  symbol: string; business_model?: string | null; stance?: string | null
  scores: Record<string, number | null>
  checks: Record<string, ResilienceCheck[]>
  flags: string[]; needs: string[]
  event?: { pct_recovered?: number; thu_ret?: number; fri_ret?: number } | null
  flow?: { footprint?: string | null; streak?: number | null;
           acc_days?: number | null; dist_days?: number | null } | null
  coverage?: { measured_share?: number; xcheck?: string; committed_evidence?: boolean }
}

export interface GuidanceCard {
  symbol: string; outlook: number | null; quality: number | null
  guidance?: { text: string; metric?: string; period?: string;
               direction?: string; normalized?: boolean }[]
  counts?: { raised?: number; lowered?: number; maintained?: number }
}
