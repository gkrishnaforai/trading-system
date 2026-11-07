import { api, type ResilienceRow } from '@/lib/api'
import { ResilienceClient } from './resilience-client'

/** Company score table — server fetches the full journal,
 *  client handles sort/search. */
export async function ResilienceTable() {
  const d = await api.resilienceAll()
  const rows = (d?.items ?? []).filter(
    r => r.scores && (r.scores.ai_opportunity != null
                      || r.scores.company_health != null))
  if (!rows.length) return null
  return <ResilienceClient rows={rows} />
}
