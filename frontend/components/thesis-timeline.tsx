import type { ThesisChangeEvent } from '@/lib/api'

const TONE: Record<string, string> = {
  on_track: 'text-aggressive',
  improving: 'text-aggressive',
  mixed: 'text-caution',
  deteriorating: 'text-defensive',
  severely_deteriorating: 'text-defensive',
  broken: 'text-defensive',
  unknown: 'text-muted',
}

const DOT: Record<string, string> = {
  on_track: 'bg-aggressive',
  improving: 'bg-aggressive',
  mixed: 'bg-caution',
  deteriorating: 'bg-defensive',
  severely_deteriorating: 'bg-defensive',
  broken: 'bg-defensive',
  unknown: 'bg-faint',
}

const CHECK_DOT: Record<string, string> = {
  pass: 'text-aggressive',
  fail: 'text-defensive',
  unknown: 'text-faint',
}

function fmtDate(d?: string) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch {
    return d
  }
}

function head(e: ThesisChangeEvent): { text: string; tone: string } {
  if (e.event_kind === 'coverage_start')
    return { text: `tracking started — ${e.status ?? 'unknown'}`, tone: 'text-muted' }
  if (e.event_kind === 'leg_change')
    return { text: `legs moved — status held ${e.status ?? '—'}`, tone: 'text-caution' }
  return {
    text: `${e.prev_status ?? '—'} → ${e.status ?? '—'}`,
    tone: TONE[e.status ?? ''] ?? 'text-muted',
  }
}

/** Thesis timeline — every journaled change with the evidence that
 *  produced it. Transitions expand to the moving legs' checks; flat
 *  days are absent by design — this is a change log, not a heartbeat. */
export function ThesisTimeline({ events }: { events?: ThesisChangeEvent[] }) {
  if (!events || events.length === 0) return null
  return (
    <div className="border-t border-hairline mt-4 pt-4">
      <div className="text-[11px] uppercase tracking-[0.15em] text-faint">
        Thesis changes
      </div>
      <div className="pt-3 space-y-4">
        {events.map((e) => {
          const h = head(e)
          const dotCls =
            e.event_kind === 'status_transition'
              ? (DOT[e.status ?? ''] ?? 'bg-faint')
              : e.event_kind === 'leg_change'
                ? 'bg-caution'
                : 'bg-faint'
          const vetoes = Array.isArray(e.veto_fired) ? e.veto_fired : []
          return (
            <div key={e.id} className="relative pl-5">
              <span
                className={`absolute left-0 top-1.5 h-2 w-2 rounded-full ${dotCls}`}
              />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="font-mono text-[11px] text-faint">
                  {fmtDate(e.as_of)}
                </span>
                <span className={`text-[12px] font-medium ${h.tone}`}>
                  {h.text}
                </span>
                {e.score != null && (
                  <span className="font-mono text-[10px] text-faint">
                    score {e.score}
                  </span>
                )}
              </div>
              {e.hyp_changes && e.hyp_changes.length > 0 && (
                <div className="pt-1.5 flex flex-wrap gap-1.5">
                  {e.hyp_changes.map((c, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-hairline px-2 py-0.5 font-mono text-[10px] text-muted"
                    >
                      {(c.id ?? '').replace(/_/g, ' ')}{' '}
                      <span className="text-faint">{c.from ?? 'new'}</span>
                      →<span className={TONE[c.to ?? ''] ?? 'text-muted'}>
                        {c.to ?? '?'}
                      </span>
                    </span>
                  ))}
                </div>
              )}
              {vetoes.length > 0 && (
                <p className="pt-1 text-[11px] text-defensive">
                  veto: {vetoes.map((v) => v.flag ?? v.id).join(' · ')}
                </p>
              )}
              {e.evidence && e.evidence.length > 0 && (
                <div className="pt-1.5 space-y-0.5">
                  {e.evidence.map((ev, i) =>
                    (ev.checks ?? []).map((c, j) => (
                      <p
                        key={`${i}-${j}`}
                        className="text-[10px] leading-relaxed text-muted"
                      >
                        <span className={CHECK_DOT[c.status ?? ''] ?? 'text-faint'}>
                          {c.status === 'pass' ? '✓' : c.status === 'fail' ? '✗' : '·'}
                        </span>{' '}
                        <span className="font-mono text-faint">
                          {ev.hypothesis_id?.replace(/_/g, ' ')}
                          {c.hard ? ' (hard)' : ''}:
                        </span>{' '}
                        {c.note ?? c.metric}
                      </p>
                    )),
                  )}
                </div>
              )}
              {e.fv_delta_pct != null && (
                <p className="pt-1 font-mono text-[10px] text-faint">
                  fv {e.fv_delta_pct >= 0 ? '+' : ''}
                  {e.fv_delta_pct}%{e.priced_in ? ` · ${e.priced_in}` : ''}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
