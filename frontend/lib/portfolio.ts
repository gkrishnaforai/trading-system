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
  created_at?: string
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
  if (!res?.ok) {
    console.warn(
      `[portfolio] list failed: ${res ? res.status : 'no response (auth?)'}`,
    )
    return []
  }
  try {
    const j = await res.json()
    return Array.isArray(j) ? j : []
  } catch {
    return []
  }
}

export async function listHoldings(id: string): Promise<Holding[]> {
  const res = await authedFetch(`/portfolios/${id}/holdings`)
  if (!res?.ok) {
    console.warn(`[portfolio] holdings ${id} failed: ${res?.status}`)
    return []
  }
  try {
    const j = await res.json()
    return Array.isArray(j) ? j : []
  } catch {
    return []
  }
}
