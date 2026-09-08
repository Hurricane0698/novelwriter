import type {
  WorldEntryHandoffState,
  WorldEntryPendingState,
} from '@/components/novel-shell/NovelShellRouteState'
import type { BootstrapJobResponse } from '@/types/api'
import { parseApiTimestamp } from '@/lib/apiTimestamp'

const PENDING_START_SKEW_MS = 1_000
export const WORLD_ENTRY_PENDING_TTL_MS = 30 * 60 * 1_000

function getBootstrapJobTimestampMs(job: BootstrapJobResponse): number | null {
  const updatedAtMs = parseApiTimestamp(job.updated_at)
  if (Number.isFinite(updatedAtMs)) return updatedAtMs
  const createdAtMs = parseApiTimestamp(job.created_at)
  return Number.isFinite(createdAtMs) ? createdAtMs : null
}

export function isWorldEntryPendingExpired(
  pending: WorldEntryPendingState | null | undefined,
  nowMs = Date.now(),
): boolean {
  if (!pending || pending.startedAtMs == null) return false
  return nowMs - pending.startedAtMs > WORLD_ENTRY_PENDING_TTL_MS
}

export function buildWorldEntryHandoffFromBootstrapJob(
  job: BootstrapJobResponse,
): WorldEntryHandoffState | null {
  if (job.status === 'failed') {
    return {
      kind: 'extract_failed',
      entityCount: null,
      relationshipCount: null,
      systemCount: null,
    }
  }

  if (job.status !== 'completed') return null
  const producedWorldData = job.result.entities_found > 0 || job.result.relationships_found > 0

  return {
    kind: job.result.index_refresh_only || !producedWorldData ? 'extract_success' : 'extract_review',
    entityCount: job.result.entities_found,
    relationshipCount: job.result.relationships_found,
    systemCount: null,
  }
}

export function resolvePendingWorldEntryHandoffFromBootstrapJob(
  pending: WorldEntryPendingState | null,
  job: BootstrapJobResponse | null | undefined,
): WorldEntryHandoffState | null {
  if (isWorldEntryPendingExpired(pending)) return null
  if (!pending || pending.kind !== 'extract' || !job) return null

  if (pending.jobId != null && job.job_id !== pending.jobId) return null

  if (pending.startedAtMs != null) {
    const jobTimestampMs = getBootstrapJobTimestampMs(job)
    if (jobTimestampMs != null && jobTimestampMs + PENDING_START_SKEW_MS < pending.startedAtMs) {
      return null
    }
  }

  return buildWorldEntryHandoffFromBootstrapJob(job)
}
