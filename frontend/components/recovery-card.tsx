import type { RecoveryVerdict } from '@/lib/api'
import { glossed } from '@/lib/terms'

const STATE_TONE: Record<string, string> = {
  RECOVERY: 'text-aggressive border-aggressive/40',
  RETEST: 'text-aggressive border-aggressive/40',
  STABILIZATION: 'text-caution border-caution/40',
  EXHAUSTION: 'text-defensive border-defensive/40',
  STRUCTURAL_IMPAIRMENT: 'text-defensive border-defensive/60',
  NORMAL: 'text-muted border-hairline',
}

const ACT_TONE: Record<string, string> = {
  ADD: 'text-aggressive', STARTER: 'text-aggressive',
  HOLD: 'text-muted', WATCH: 'text-caution',
  TRIM: 'text-defensive', AVOID: 'text-defensive', EXIT: 'text-defensive',
}

/** Recovery verdict — the composition layer's one answer: state,
 *  advisory action, what must happen next, what invalidates, and
 *  where the engines disagree. Phase-1: explains, never instructs. */
export function RecoveryCard({ v }: { v?: RecoveryVerdict | null }) {
  if (!v?.state) return null
  const gates = v.gates ?? {}
  const failed = Object.entries(gates).filter(([, ok]) => ok === false)
  const conflicts = v.conflicts ?? []
  return (
    <section className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Recovery verdict · advisory
        </span>
        <span className="font-mono text-[11px] text-faint">
          {v.as_of}{v.state_changed ? ' · changed' : ''}
        </span>
      </div>
      <div className="pt-2 flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-3 py-1 text-[12px] font-semibold ${STATE_TONE[v.state] ?? 'text-muted border-hairline'}`}>
          {glossed(v.state)}
        </span>
        {v.prev_state && v.state_changed && (
          <span className="font-mono text-[11px] text-faint">
            {v.prev_state.replace(/_/g, ' ')} →
          </span>
        )}
        {v.decision && (
          <span className={`font-mono text-[12px] font-semibold ${ACT_TONE[v.decision] ?? 'text-muted'}`}>
            {v.decision}
            {v.decision_confidence && v.decision_confidence !== 'normal' && (
              <span className="text-faint font-normal"> ({v.decision_confidence})</span>
            )}
          </span>
        )}
        {!!v.event_type && (
          <span className="text-[11px] text-faint">
            event: {String(v.event_type).replace(/_/g, ' ')}
          </span>
        )}
      </div>
      {conflicts.length > 0 && (
        <div className="pt-2 space-y-1">
          {conflicts.map((c, i) => (
            <p key={i} className="text-[11px] leading-relaxed text-caution">
              ⚠ {String(c.note)}
            </p>
          ))}
        </div>
      )}
      {(v.required_confirmation?.length || v.invalidation_conditions?.length) ? (
        <div className="pt-2 grid gap-3 sm:grid-cols-2">
          {!!v.required_confirmation?.length && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-faint">to confirm</p>
              <ul className="pt-1 space-y-0.5">
                {v.required_confirmation.map((x, i) => (
                  <li key={i} className="text-[11px] text-muted">· {x}</li>
                ))}
              </ul>
            </div>
          )}
          {!!v.invalidation_conditions?.length && (
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-faint">invalidates</p>
              <ul className="pt-1 space-y-0.5">
                {v.invalidation_conditions.map((x, i) => (
                  <li key={i} className="text-[11px] text-defensive/80">· {x}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : null}
      {failed.length > 0 && (
        <p className="pt-2 font-mono text-[10px] text-faint">
          gates failing: {failed.map(([k]) => k.replace(/_/g, ' ')).join(' · ')}
        </p>
      )}
      {!!v.missing_inputs?.length && (
        <p className="pt-1 font-mono text-[10px] text-faint">
          missing inputs (not scored): {v.missing_inputs.join(', ')}
        </p>
      )}
    </section>
  )
}
