type Report = {
  stance?: string
  likes?: string[]
  confirm?: string[]
  status?: string
  dir?: string
  archetype?: string
}

const STANCE_TONE: Record<string, string> = {
  accumulate: 'text-aggressive',
  'on track': 'text-aggressive',
  avoid: 'text-defensive',
  reduce: 'text-defensive',
  insufficient: 'text-muted',
}

function stanceTone(s?: string): string {
  const k = (s ?? '').toLowerCase()
  for (const [key, cls] of Object.entries(STANCE_TONE)) {
    if (k.startsWith(key)) return cls
  }
  return 'text-caution' // watch / hold family
}

/** 'What I like / what I want confirmed' — deterministic thesis
 *  report rendered from symbol_thesis hypotheses. Every bullet cites
 *  the engine check that produced it; unknown legs are asks, not
 *  scores. */
export function ThesisReport({ report }: { report?: Report | null }) {
  if (!report?.stance) return null
  const likes = report.likes ?? []
  const confirm = report.confirm ?? []
  return (
    <div className="border-t border-hairline mt-4 pt-4">
      <div className="flex items-baseline justify-between gap-3">
        <span
          className={`text-sm font-semibold ${stanceTone(report.stance)}`}
        >
          {report.stance}
        </span>
        {report.archetype && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
            {String(report.archetype).replace(/_/g, ' ')}
          </span>
        )}
      </div>
      {likes.length > 0 && (
        <div className="pt-3">
          <div className="text-[11px] uppercase tracking-[0.15em] text-faint">
            What I like
          </div>
          <ul className="pt-1.5 space-y-1">
            {likes.map((l, i) => (
              <li key={i} className="text-xs leading-relaxed text-muted">
                <span className="text-aggressive">· </span>
                {l}
              </li>
            ))}
          </ul>
        </div>
      )}
      {confirm.length > 0 && (
        <div className="pt-3">
          <div className="text-[11px] uppercase tracking-[0.15em] text-faint">
            What I want confirmed
          </div>
          <ul className="pt-1.5 space-y-1">
            {confirm.map((c, i) => (
              <li key={i} className="text-xs leading-relaxed text-muted">
                <span className="text-caution">· </span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
