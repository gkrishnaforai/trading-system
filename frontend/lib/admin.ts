import { getRaw } from './api'

export type JobRow = {
  name: string
  label?: string
  purpose?: string
  kind?: string
  cron?: string | null
  enabled?: boolean
  depends_on?: string[] | null
  priority?: number
  last_run?: string | null
  last_error?: string | null
  duration_s?: number | null
  next_run?: string | null
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

export async function incidents(): Promise<Record<string, unknown> | null> {
  return getRaw<Record<string, unknown>>(
    '/api/v1/board/incidents', { fresh: true })
}
