type ThesisChange = {
  id?: string
  archetype?: string
  from?: string
  to?: string
}

export type Thesis = {
  archetype?: string
  status?: string
  status_dir?: string
  prev_status?: string
  status_since?: string
  score?: number
  hyp_changes?: ThesisChange[]
  detail?: { unresolved?: string[] }
}

const STATUS_TONE: Record<string, string> = {
  on_track: 'text-aggressive',
  improving: 'text-aggressive',
  mixed: 'text-caution',
  deteriorating: 'text-defensive',
  broken: 'text-defensive',
  unknown: 'text-muted',
}

const DOT: Record<string, string> = {
  on_track: 'bg-aggressive',
  improving: 'bg-aggressive',
  mixed: 'bg-caution',
  deteriorating: 'bg-defensive',
  broken: 'bg-defensive',
  unknown: 'bg-faint',
}

const DIR_GLYPH: Record<string, { g: string; cls: string }> = {
  up: { g: '▲', cls: 'text-aggressive' },
  down: { g: '▼', cls: 'text-defensive' },
  flat: { g: '●', cls: 'text-faint' },
  new: { g: '✦', cls: 'text-accent' },
}

function title(t: Thesis): string {
  const lines: string[] = []
  if (t.prev_status && t.status !== t.prev_status) {
    lines.push(`was ${t.prev_status} → now ${t.status}`)
  }
  for (const c of t.hyp_changes ?? []) {
    if (c?.id) lines.push(`${c.id}: ${c.from} → ${c.to}`)
  }
  const unr = t.detail?.unresolved
  if (unr?.length) {
    lines.push('', 'unresolved:')
    for (const u of unr.slice(0, 4)) lines.push(`· ${u}`)
  }
  return lines.join('\n')
}

/** Archetype-thesis flag — colored dot for status, arrow for the
 *  nightly delta (▲ improving / ▼ deteriorating / ● continuing /
 *  ✦ first eval). Title tooltip lists which legs just moved. */
export function ThesisFlag({ thesis }: { thesis?: Thesis | null }) {
  if (!thesis?.status) return null
  const st = String(thesis.status)
  const dir = DIR_GLYPH[String(thesis.status_dir ?? 'flat')]
    ?? DIR_GLYPH.flat
  return (
    <span
      title={title(thesis) || 'archetype thesis'}
      className={`inline-flex items-center gap-1.5 rounded-full border border-hairline px-2.5 py-0.5 text-[10px] font-semibold tracking-wider ${STATUS_TONE[st] ?? 'text-muted'}`}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${DOT[st] ?? 'bg-faint'}`}
      />
      thesis {st.replace('_', ' ')}
      <span className={dir.cls}>{dir.g}</span>
    </span>
  )
}
