/** Access tiers — public (anonymous) → member (free account) → pro
    (paid). The layer exists so every section carries its minimum tier
    now; when auth lands, only currentTier() changes. Until then we
    browse as the top tier so all functionality stays reachable. */

export type Tier = 'public' | 'member' | 'pro'

export const TIER_ORDER: Record<Tier, number> = {
  public: 0, member: 1, pro: 2,
}

/** What each capability requires.
    public   — the hook: regime, calendar, receipts (the ledger sells
               itself), top-line stock card.
    member   — the habit: live daily board, full stock detail.
    pro      — the desk: valuation methods, capex legs, detail dumps,
               readiness internals. */
export const FEATURE_TIER: Record<string, Tier> = {
  regime: 'public',
  calendar: 'public',
  receipts: 'public',
  stock_card: 'public',
  board: 'member',
  stock_detail: 'member',
  fv_methods: 'pro',
  capex_legs: 'pro',
  detail_sections: 'pro',
}

export function currentTier(): Tier {
  // TODO(auth): read the session → 'public' anonymous, 'member' free
  // signup, 'pro' paid. Default pro while there is no login wall.
  return 'pro'
}

export function canSee(feature: string, tier: Tier = currentTier()) {
  const need = FEATURE_TIER[feature] ?? 'public'
  return TIER_ORDER[tier] >= TIER_ORDER[need]
}

export function tierLabel(feature: string) {
  const need = FEATURE_TIER[feature] ?? 'public'
  return need === 'pro' ? 'Pro' : need === 'member' ? 'Member' : 'Free'
}
