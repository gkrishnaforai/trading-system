import { getUser } from '@/lib/auth'
import { jobCatalog, jobRuns, incidents, type JobRow } from '@/lib/admin'
import { JobActions, RunAll } from '@/components/admin-jobs'
import AdminFv from '@/components/admin-fv'

export const dynamic = 'force-dynamic'

function ago(iso?: string | null) {
  if (!iso) return 'never'
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000)
  if (s < 90) return `${Math.floor(s)}s ago`
  if (s < 5400) return `${Math.floor(s / 60)}m ago`
  if (s < 129600) return `${(s / 3600).toFixed(1)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

function until(iso?: string | null) {
  if (!iso) return '—'
  const s = (Date.parse(iso) - Date.now()) / 1000
  if (s < 0) return 'due'
  if (s < 5400) return `in ${Math.floor(s / 60)}m`
  if (s < 129600) return `in ${(s / 3600).toFixed(1)}h`
  return `in ${(s / 86400).toFixed(1)}d`
}

function fmtDur(s?: number | null) {
  if (s == null) return ''
  if (s < 90) return `${Math.round(s)}s`
  return `${(s / 60).toFixed(1)}m`
}

function JobRowView({ j }: { j: JobRow }) {
  const err = j.last_error
  return (
    <div className="grid grid-cols-12 items-start gap-3 py-3 border-b border-hairline/60 last:border-0">
      <div className="col-span-12 md:col-span-4 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-ink">
            {j.label ?? j.name}
          </span>
          <span className="font-mono text-[10px] text-faint">{j.name}</span>
        </div>
        {j.purpose && (
          <p className="pt-0.5 text-xs text-muted leading-snug">{j.purpose}</p>
        )}
        {Array.isArray(j.depends_on) && j.depends_on.length > 0 && (
          <p className="pt-0.5 font-mono text-[10px] text-faint">
            deps: {j.depends_on.join(', ')}
          </p>
        )}
      </div>
      <div className="col-span-6 md:col-span-2 font-mono text-xs">
        {j.cron ? (
          <>
            <div className="text-ink">{j.cron}</div>
            <div className="text-[10px] text-faint">{j.timezone ?? 'UTC'} · next {until(j.next_run)}</div>
          </>
        ) : (
          <span className="text-faint">manual</span>
        )}
      </div>
      <div className="col-span-3 md:col-span-2 text-xs">
        <span className={`inline-flex items-center gap-1.5 ${j.enabled ? 'text-aggressive' : 'text-faint'}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${j.enabled ? 'bg-aggressive' : 'bg-faint'}`} />
          {j.enabled ? 'on' : 'off'}
        </span>
        {j.running ? (
          <div className="pt-1 font-mono text-[11px] text-accent">
            ● running · started {ago(j.started_at)}
          </div>
        ) : (
          <div className={`pt-1 font-mono text-[11px] ${err ? 'text-defensive' : 'text-muted'}`}>
            {ago(j.last_run)}
            {j.duration_s != null && ` · ${fmtDur(j.duration_s)}`}
          </div>
        )}
        {err && (
          <div className="pt-0.5 text-[10px] leading-snug text-defensive">
            {String(err).slice(0, 90)}
          </div>
        )}
      </div>
      <div className="col-span-3 md:col-span-4 flex justify-end">
        <JobActions name={j.name} enabled={!!j.enabled} cron={j.cron ?? null} />
      </div>
    </div>
  )
}

export default async function AdminPage() {
  const u = await getUser()
  if (u.role !== 'admin') {
    return (
      <main className="mx-auto max-w-3xl px-5 pb-20">
        <header className="pt-6 pb-8">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Ops
          </div>
          <h1 className="pt-3 font-semibold text-display text-ink">
            Admin <span className="text-accent">desk</span>
          </h1>
        </header>
        <section className="rounded-xl border border-hairline bg-card px-5 py-6 text-sm text-muted">
          This surface is admin-only. The current session
          {u.username ? ` (${u.username})` : ''} isn&apos;t an admin —
          add the username to <span className="font-mono text-xs">MP_ADMIN_USERS</span>{' '}
          on the worker or set <span className="font-mono text-xs">role=admin</span>{' '}
          on the user row, then reload.
        </section>
      </main>
    )
  }

  const [jobs, runs, inc] = await Promise.all([
    jobCatalog(), jobRuns(20), incidents(),
  ])

  const open = Array.isArray(inc?.open) ? (inc.open as unknown[]) : []
  const actions = Array.isArray(inc?.actions) ? (inc.actions as Record<string, unknown>[]) : []
  const errors = jobs.filter((j) => j.last_error).length
  const scheduled = jobs.filter((j) => j.enabled && j.cron).length

  return (
    <main className="mx-auto max-w-4xl px-5 pb-20">
      <header className="pt-6 pb-6 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Ops
          </div>
          <h1 className="pt-3 font-semibold text-display text-ink">
            Admin <span className="text-accent">desk</span>
          </h1>
          <p className="pt-3 max-w-xl text-[13px] leading-relaxed text-muted">
            {jobs.length} jobs · {scheduled} scheduled ·{' '}
            {errors > 0
              ? <span className="text-defensive">{errors} last-runs errored</span>
              : <span className="text-aggressive">all last-runs clean</span>}
            {open.length > 0 && (
              <span className="text-caution"> · {open.length} open incidents</span>
            )}
          </p>
        </div>
        <RunAll />
      </header>

      {/* job catalog — schedule + run controls */}
      <section className="rounded-xl border border-hairline bg-card px-5 py-2">
        {jobs.length === 0 ? (
          <p className="py-6 text-sm text-muted">
            No jobs registered — the worker may be unreachable.
          </p>
        ) : (
          jobs.map((j) => <JobRowView key={j.name} j={j} />)
        )}
      </section>

      {/* recent dispatcher runs */}
      <section className="mt-6 rounded-xl border border-hairline bg-card px-5 py-4">
        <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
          Recent runs
        </div>
        <div className="pt-3 divide-y divide-hairline/60">
          {runs.length === 0 && (
            <p className="text-sm text-muted py-2">No runs on record.</p>
          )}
          {runs.map((r, i) => (
            <div key={i} className="flex items-baseline justify-between gap-4 py-1.5 text-xs">
              <span className="flex items-center gap-2 min-w-0">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${r.error ? 'bg-defensive' : 'bg-aggressive'}`} />
                <span className="font-medium text-ink">{r.name}</span>
                {r.error && (
                  <span className="truncate text-defensive">{String(r.error).slice(0, 80)}</span>
                )}
              </span>
              <span className="shrink-0 font-mono text-faint">
                {ago(r.ran_at)}
                {r.duration_s != null && ` · ${fmtDur(r.duration_s)}`}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* fair-value recompute */}
      <section className="mt-6 rounded-xl border border-hairline bg-card px-5 py-4">
        <AdminFv />
      </section>

      {/* custodian incidents */}
      {actions.length > 0 && (
        <section className="mt-6 rounded-xl border border-hairline bg-card px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-faint">
            Custodian actions
          </div>
          <div className="pt-3 space-y-1.5">
            {actions.slice(0, 8).map((a, i) => (
              <div key={i} className="text-xs text-muted">
                <span className="text-ink">{String(a.action ?? a.kind ?? 'action')}</span>
                {a.detail != null && ` — ${String(a.detail).slice(0, 120)}`}
                {a.at != null && (
                  <span className="font-mono text-faint"> · {ago(String(a.at))}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <footer className="mt-16 border-t border-hairline pt-6 text-[11px] text-faint">
        dispatcher ticks every 60s · cron uses each job's timezone ·
        paused jobs still accept manual runs
      </footer>
    </main>
  )
}
