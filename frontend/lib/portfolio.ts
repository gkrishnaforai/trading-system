import { authedFetch } from './auth'

export type Portfolio = {
  id: string
  name: string
  description?: string | null
  portfolio_type?: string
  initial_capital?: number
  currency?: string
  holdings_count?: number
  total_invested?: number
}

export type Holding = {
  id: string
  symbol: string
  asset_type?: string
  shares_held?: number
  average_cost?: number
  total_cost?: number
  status?: string
  notes?: string | null
  company_name?: string | null
  sector?: string | null
}

export async function listPortfolios(): Promise<Portfolio[]> {
  const res = await authedFetch('/portfolios')
  if (!res?.ok) return []
  try {
    const j = await res.json()
    return Array.isArray(j) ? j : []
  } catch {
    return []
  }
}

export async function listHoldings(id: string): Promise<Holding[]> {
  const res = await authedFetch(`/portfolios/${id}/holdings`)
  if (!res?.ok) return []
  try {
    const j = await res.json()
    return Array.isArray(j) ? j : []
  } catch {
    return []
  }
}
