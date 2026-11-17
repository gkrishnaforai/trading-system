/** Plain-English glosses for engine vocabulary — bracketed inline so
 *  users who aren't fluent in market jargon can still read the page.
 *  Keep glosses short: they render inside the flow, not as tooltips. */

export const TERM_GLOSS: Record<string, string> = {
  // regime / macro states
  risk_on: 'confident mood — investors buying growth',
  strong_risk_on: 'confident mood — investors buying growth',
  risk_off: 'defensive mood — money moving to safety',
  mildly_risk_off: 'slightly defensive mood',
  macro_risk_off: 'defensive mood — money moving to safety',
  stress: 'panic conditions — forced selling',
  transition: 'regime changing — signals disagree',
  range_chop: 'sideways, no clear trend',
  neutral: 'no strong signal either way',
  bear: 'downtrend',
  bear_bounce: 'rally inside a downtrend — may not last',
  bull: 'uptrend',
  bull_low_vol: 'uptrend with low volatility',
  bull_high_vol: 'uptrend but volatile — bumpier ride',
  bullish_correction: 'pullback inside an uptrend',
  bullish: 'uptrend',
  bullish_weakening: 'uptrend losing momentum',
  bearish: 'downtrend',
  under_pressure: 'sellers have the edge',
  recovering: 'healing after weakness',

  // intraday tape states
  tape_breaking: 'selloff accelerating — live tape deteriorating',
  sellers_regaining: 'sellers back in control this session',
  sellers_tiring: 'selling pressure fading',
  buyers_regaining: 'buyers back in control this session',
  buyers_in_control: 'buyers in control this session',
  relief_rally: 'bounce after a selloff — may not hold',
  vwap_reclaim: 'price back above the session average — dip buyers winning',
  vwap_loss: 'price lost the session average — sellers winning',
  stabilizing: 'selloff slowing — early repair',

  // breadth / participation
  breadth: 'how many stocks are participating, not just the index',
}

/** "risk_off" → "safety over growth" (bare gloss), for appending. */
export function glossOf(v?: string | null): string | null {
  if (!v) return null
  return TERM_GLOSS[v] ?? null
}

/** "risk_off" → "risk off (defensive — money to safety)". */
export function glossed(v?: string | null): string {
  const label = (v ?? '—').replace(/_/g, ' ')
  const g = glossOf(v)
  return g ? `${label} (${g})` : label
}
