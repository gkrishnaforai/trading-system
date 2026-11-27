import { getRaw } from './api'

export type JobRow = {
  name: string
  label?: string
  purpose?: string
  kind?: string
  cron?: string | null
  timezone?: string | null
  enabled?: boolean
  depends_on?: string[] | null
  priority?: number
  last_run?: string | null
  last_error?: string | null
  duration_s?: number | null
  next_run?: string | null
  running?: boolean
  started_at?: string | null
}

export type JobRun = {
  name: string
  ran_at?: string
  duration_s?: number | null
  error?: string | null
  result?: unknown
}

export async function jobCatalog(): Promise<JobRow[]> {
  const j = await getRaw<{ jobs?: JobRow[] }>(
    '/api/v1/board/jobs/catalog', { fresh: true })
  return j?.jobs ?? []
}

export async function jobRuns(limit = 25): Promise<JobRun[]> {
  const j = await getRaw<{ runs?: JobRun[] }>(
    `/api/v1/board/jobs/runs?limit=${limit}`, { fresh: true })
  return j?.runs ?? []
}

export type SystemHealth = {
  heartbeat?: { last_job_at?: string | null; silent_min?: number | null }
  queue?: { pending?: number; failed?: number }
  provider_failures_24h?: { count?: number; providers?: number }
  job_errors_24h?: number
  jobs_last_hour?: number
}

export async function systemHealth(): Promise<SystemHealth | null> {
  return getRaw<SystemHealth>(
    '/api/v1/board/system-health', { fresh: true })
}
