/** Access tiers — public (anonymous) → member (free account) → pro
    (paid) → elite (highest paid). The layer exists so every section
    carries its minimum tier now; when auth lands, only currentTier()
    changes. Until then we browse as the top tier so all functionality
    stays reachable. */

export type Tier = 'public' | 'member' | 'pro' | 'elite'

export const TIER_ORDER: Record<Tier, number> = {
  public: 0, member: 1, pro: 2, elite: 3,
}

/** Per-tier object limits — enforced when per-user portfolios ship. */
export const TIER_LIMITS: Record<Tier, { portfolios: number; watchlists: number }> = {
  public: { portfolios: 0, watchlists: 0 },
  member: { portfolios: 1, watchlists: 1 },
  pro: { portfolios: 5, watchlists: 5 },
  elite: { portfolios: 20, watchlists: 20 },
}

/** What each capability requires.
    public   — the hook: regime, calendar, receipts (the ledger sells
               itself), top-line stock card.
    member   — the habit: live daily board, full stock detail, one
               portfolio, one watchlist.
    pro      — the desk: valuation methods, capex legs, detail dumps,
               five portfolios.
    elite    — the book-of-books: twenty portfolios, everything open. */
export const FEATURE_TIER: Record<string, Tier> = {
  regime: 'public',
  calendar: 'public',
  receipts: 'public',
  stock_card: 'public',
  board: 'member',
  stock_detail: 'member',
  portfolio: 'member',
  watchlist: 'member',
  alerts: 'member',
  fv_methods: 'pro',
  capex_legs: 'pro',
  detail_sections: 'pro',
}

export function currentTier(): Tier {
  // TODO(auth): read the session → 'public' anonymous, 'member' free
  // signup, 'pro' paid, 'elite' top plan. Default elite while there
  // is no login wall — everything browsable.
  return 'elite'
}

export function canSee(feature: string, tier: Tier = currentTier()) {
  const need = FEATURE_TIER[feature] ?? 'public'
  return TIER_ORDER[tier] >= TIER_ORDER[need]
}

export function tierLabel(feature: string) {
  const need = FEATURE_TIER[feature] ?? 'public'
  return need === 'elite' ? 'Elite'
    : need === 'pro' ? 'Pro'
      : need === 'member' ? 'Member' : 'Free'
}
