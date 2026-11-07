import { api } from '@/lib/api'

/** Resilience screener — sortable-by-score list riding the
 *  company_resilience_scores journal. Health = business quality,
 *  AI = ai-opportunity, Tape = tape resilience. Flags disclose
 *  validation findings (unverified facts, contradictions). */
export async function ResilienceTable() {
  const d = await api.resilienceAll()
  const rows = (d?.items ?? [])
    .filter(r => r.scores && (r.scores.ai_opportunity != null
                              || r.scores.company_health != null))
    .sort((a, b) =>
      (b.scores?.ai_opportunity ?? b.scores?.company_health ?? -1)
      - (a.scores?.ai_opportunity ?? a.scores?.company_health ?? -1))
    .slice(0, 40)
  if (!rows.length) return null
  return (
    <div className="mt-5">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted">
        Company scores — health · ai · tape
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-1 pr-3 font-medium">sym</th>
              <th className="py-1 pr-3 font-medium">hlth</th>
              <th className="py-1 pr-3 font-medium">ai</th>
              <th className="py-1 pr-3 font-medium">tape</th>
              <th className="py-1 pr-3 font-medium">dep</th>
              <th className="py-1 pr-3 font-medium">model</th>
              <th className="py-1 font-medium">flags / needs</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const sc = r.scores ?? {}
              const meta = [...(r.flags ?? []), ...(r.needs ?? []).map((n: string) => `needs: ${n}`)]
              return (
                <tr key={r.symbol} className="border-t border-line/40">
                  <td className="py-1.5 pr-3 font-medium text-ink">
                    <a href={`/stock?symbol=${r.symbol}`}>{r.symbol}</a>
                  </td>
                  <td className="py-1.5 pr-3">{sc.company_health ?? '—'}</td>
                  <td className="py-1.5 pr-3">{sc.ai_opportunity ?? '—'}</td>
                  <td className="py-1.5 pr-3">{sc.tape_resilience ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-muted">{sc.deployment_risk ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-muted">{(r.business_model ?? '').replaceAll('_', ' ')}</td>
                  <td className="py-1.5 text-muted">{meta.slice(0, 3).join(' · ') || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
