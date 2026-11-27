import Link from 'next/link'
import { Section } from '@/components/regime'
import { ApiRunner } from '@/components/api-playground'

type Entry = {
  method: 'GET' | 'POST'
  path: string
  desc: string
  fields?: { name: string; placeholder?: string }[]
}

const GROUPS: { title: string; note?: string; entries: Entry[] }[] = [
  {
    title: 'Earnings reports',
    note: 'versioned per-print reports — journaled by earnings-watch, lazy-composed on first read',
    entries: [
      { method: 'GET', path: 'earnings-report/{sym}', desc: 'latest report version for a symbol — composes v1 on the fly if none exists', fields: [{ name: 'sym', placeholder: 'PLTR' }] },
      { method: 'GET', path: 'earnings-report/{sym}?date=', desc: 'report for a specific print date — add &version=N for a pinned version', fields: [{ name: 'sym', placeholder: 'PLTR' }, { name: 'date', placeholder: '2026-11-02' }] },
      { method: 'GET', path: 'earnings-report/{sym}/versions', desc: 'every journaled report version — the audit list', fields: [{ name: 'sym', placeholder: 'PLTR' }] },
      { method: 'GET', path: 'earnings-reports?days=60', desc: 'latest-version reports across the book — the feed' },
      { method: 'POST', path: 'earnings-report/{sym}/rebuild?date=', desc: 'backfill/rebuild — appends a new version for a past print', fields: [{ name: 'sym', placeholder: 'PLTR' }, { name: 'date', placeholder: '2026-08-04' }] },
    ],
  },
  {
    title: 'Forward EPS integrity',
    note: 'wrong-fiscal-year guard — audit first (read-only), then repair',
    entries: [
      { method: 'GET', path: 'fwd-eps-audit', desc: 'every stored fwd EPS that fails TTM-ratio or snapshot-year checks' },
      { method: 'POST', path: 'refresh/fwd-eps-repair', desc: 'audit → recompute suspects → re-resolve FV where EPS moved >10%' },
    ],
  },
  {
    title: 'Jobs',
    note: 'manual runs go through the same _run_job path as the scheduler — journaled to job_runs',
    entries: [
      { method: 'GET', path: 'jobs/catalog', desc: 'all jobs — schedule, timezone, enabled state' },
      { method: 'GET', path: 'jobs/runs?hours=48', desc: 'recent job runs — status, duration, error' },
      { method: 'POST', path: 'refresh/{job}', desc: 'run a job now — e.g. morning-regime, flywheel, fv-sweep', fields: [{ name: 'job', placeholder: 'morning-regime' }] },
      { method: 'POST', path: 'earnings-watch', desc: 'run the earnings watcher sweep now' },
    ],
  },
  {
    title: 'Regime & pulse',
    entries: [
      { method: 'GET', path: 'morning-regime', desc: 'daily canonical regime baseline + intraday overlay + fragility + tape' },
      { method: 'GET', path: 'fragility', desc: 'systematic selling early warning — vulnerability 0-100 + 1/3/5/10d trigger probabilities (per-leg observed/estimated status)' },
      { method: 'GET', path: 'metals-pulse', desc: 'metals regime + opportunity scores' },
      { method: 'GET', path: 'intraday', desc: 'latest 15-min tape classification' },
      { method: 'POST', path: 'refresh/fragility', desc: 'recompute SSEW now — snapshots leveraged-ETF AUM first' },
      { method: 'POST', path: 'refresh/intraday-tape', desc: 'run the intraday tape classifier job now' },
    ],
  },
  {
    title: 'Forward outlook & options',
    note: 'deterministic engines — observed analog outcomes and scenario-weighted option P&L, not calibrated forecasts',
    entries: [
      { method: 'GET', path: 'forward-outlook', desc: 'market analogs → forward outcome stats at 5d-252d + book event study' },
      { method: 'GET', path: 'forward-outlook?sym={sym}', desc: 'adds the stock forward baseline + per-symbol earnings event study', fields: [{ name: 'sym', placeholder: 'PLTR' }] },
      { method: 'GET', path: 'expected-option-pnl?sym={sym}&strike={strike}&expiry={expiry}&premium={premium}&iv={iv}', desc: 'call expected P&L under FV scenario blend — pass the chain quote you\'re evaluating', fields: [{ name: 'sym', placeholder: 'PLTR' }, { name: 'strike', placeholder: '200' }, { name: 'expiry', placeholder: '2026-08-21' }, { name: 'premium', placeholder: '12.50' }, { name: 'iv', placeholder: '0.45' }] },
    ],
  },
  {
    title: 'Symbol data',
    entries: [
      { method: 'GET', path: 'symbol/{sym}/health', desc: 'stock card — multiples, stance, flywheel, FV, readiness', fields: [{ name: 'sym', placeholder: 'PLTR' }] },
      { method: 'GET', path: 'symbol/{sym}/fv-resolve?force=true', desc: 'recompute FV bypassing the run cache — use after engine code changes', fields: [{ name: 'sym', placeholder: 'COHR' }] },
      { method: 'GET', path: 'theme/{key}/composition', desc: 'theme member comparison — P/E, PEG, growth, backlog, FV upside, ranked', fields: [{ name: 'key', placeholder: 'ai_infra' }] },
      { method: 'GET', path: 'sector-timing', desc: 'sector bottom/rebound two-score state machine per sector' },
      { method: 'GET', path: 'earnings-watch?days=7', desc: 'recent print captures — verdicts + surprises' },
      { method: 'GET', path: 'trade-plans/suggest?sym={sym}&uc=swing', desc: 'engine-proposed plan — stop, targets, trail rule', fields: [{ name: 'sym', placeholder: 'PWR' }] },
    ],
  },
]

const TONE: Record<string, string> = {
  GET: 'border-aggressive/40 text-aggressive',
  POST: 'border-caution/40 text-caution',
}

export default function ApisPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-16">
      <div className="pt-8 pb-2">
        <h1 className="text-sm font-medium tracking-wide uppercase text-muted">
          APIs — worker endpoints
        </h1>
        <p className="pt-2 text-xs text-faint leading-relaxed">
          Every useful worker URL in one place. GET links open through the
          admin proxy; POST entries have a run form. Worker paths shown
          are under <span className="font-mono">/api/v1/board/</span> —
          direct worker base is{' '}
          <span className="font-mono">http://86.38.205.58:8001</span>.
        </p>
      </div>

      {GROUPS.map(g => (
        <Section key={g.title} title={g.title} subtitle={g.note} defaultOpen>
          <div className="space-y-1">
            {g.entries.map((e, i) => (
              <div key={i} className="border-b border-hairline/50 py-2.5">
                <div className="flex flex-wrap items-baseline gap-3">
                  <span className={`rounded border px-1.5 py-0.5 text-[9.5px] font-semibold tracking-wider ${TONE[e.method]}`}>
                    {e.method}
                  </span>
                  <span className="font-mono text-xs text-ink break-all">
                    /api/v1/board/{e.path}
                  </span>
                  {e.method === 'GET' && !e.fields && (
                    <a
                      href={`/api/admin/${e.path}`}
                      target="_blank"
                      className="font-mono text-[10px] text-accent underline decoration-dotted hover:text-aggressive"
                    >
                      open →
                    </a>
                  )}
                </div>
                <div className="pt-1 text-xs text-muted">{e.desc}</div>
                {e.fields && e.method === 'GET' && (
                  <GetLink entry={e} />
                )}
                {e.method === 'POST' && (
                  <ApiRunner method={e.method} path={e.path} fields={e.fields} />
                )}
              </div>
            ))}
          </div>
        </Section>
      ))}

      <Section title="Pages" subtitle="the UI surfaces these endpoints feed">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          {[
            ['/earnings', 'earnings feed'],
            ['/earnings?sym=PLTR', 'PLTR report'],
            ['/calendar', 'earnings calendar'],
            ['/stock?sym=PLTR', 'stock card'],
            ['/', 'regime board'],
            ['/admin', 'jobs & scheduler'],
          ].map(([href, label]) => (
            <Link key={href} href={href}
                  className="rounded border border-hairline px-3 py-2 text-muted hover:text-ink hover:border-muted">
              {label}
              <span className="block text-[9px] text-faint">{href}</span>
            </Link>
          ))}
        </div>
      </Section>
    </main>
  )
}

function GetLink({ entry }: { entry: Entry }) {
  // GETs with a required {sym} field can't be static links — render a
  // mini form via the same runner component (it GETs through proxy)
  return <ApiRunner method={entry.method} path={entry.path} fields={entry.fields} />
}
