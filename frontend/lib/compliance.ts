/** Compliance feature flags — the release gate for functionality that
    may require securities-law review before it can be offered.

    Every flag defaults to FALSE (disabled) unless the matching env var
    is explicitly 'on'. A feature behind one of these must not ship —
    or silently turn on — without documented legal approval. The env
    vars are set only by an operator after that review; nothing in code
    should bypass a flag via an alternate route or API.

    When a flagged feature is built:
      1. implement it behind the flag check,
      2. document the legal assessment + approval,
      3. operator sets the env var,
      4. record the enablement in the audit log.
 */
const on = (v?: string) => v === 'on'

export const COMPLIANCE_FLAGS = {
  /** AI or engine output addressed to the individual user —
      "you should buy/sell X". Highest adviser-registration risk. */
  personalized_stock_recommendations:
    on(process.env.FF_PERSONALIZED_RECOMMENDATIONS),

  /** per-user buy/sell/hold instructions or allocation advice */
  individualized_portfolio_advice:
    on(process.env.FF_INDIVIDUALIZED_ADVICE),

  /** system picks the user's holdings for them */
  automated_portfolio_allocation:
    on(process.env.FF_AUTOMATED_ALLOCATION),

  /** system rebalances without per-action user direction */
  automated_rebalancing:
    on(process.env.FF_AUTOMATED_REBALANCING),

  /** order routing / execution — broker-dealer territory */
  live_trading: on(process.env.FF_LIVE_TRADING),

  /** next-session market direction score — a model-generated market
      forecast; stays internal/admin until reviewed */
  market_forecast: on(process.env.FF_MARKET_FORECAST),

  /** paid promotion of securities — Section 17(b) exposure */
  sponsored_stock_promotions:
    on(process.env.FF_SPONSORED_STOCK_PROMOTIONS),

  /** compensation tied to brokerage deposits/trades —
      transaction-based compensation is a BD-registration factor */
  securities_transaction_referrals:
    on(process.env.FF_TRANSACTION_REFERRALS),
} as const

export type ComplianceFlag = keyof typeof COMPLIANCE_FLAGS

/** Gate helper — callers get a reason string for logs/UI, never a
    bare false that looks like a bug. */
export function flagBlocked(flag: ComplianceFlag): string | null {
  return COMPLIANCE_FLAGS[flag]
    ? null
    : `feature '${flag}' is disabled pending legal approval`
}
