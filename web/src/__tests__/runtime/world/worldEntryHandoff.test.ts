// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildWorldEntryHandoffFromBootstrapJob,
  resolvePendingWorldEntryHandoffFromBootstrapJob,
} from '@/lib/worldEntryHandoff'
import type { WorldEntryPendingState } from '@/components/novel-shell/NovelShellRouteState'
import type { BootstrapJobResponse } from '@/types/api'

function buildCompletedJob(overrides?: Partial<BootstrapJobResponse>): BootstrapJobResponse {
  return {
    job_id: 1,
    novel_id: 1,
    mode: 'initial',
    initialized: true,
    status: 'completed',
    progress: { step: 5, detail: 'Done' },
    result: {
      entities_found: 0,
      relationships_found: 0,
      index_refresh_only: false,
    },
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('worldEntryHandoff', () => {
  it('treats zero-result extraction completion as success instead of review', () => {
    expect(buildWorldEntryHandoffFromBootstrapJob(buildCompletedJob())).toEqual({
      kind: 'extract_success',
      entityCount: 0,
      relationshipCount: 0,
      systemCount: null,
    })
  })

  it('keeps non-empty extraction completion reviewable', () => {
    expect(buildWorldEntryHandoffFromBootstrapJob(buildCompletedJob({
      result: {
        entities_found: 1,
        relationships_found: 0,
        index_refresh_only: false,
      },
    }))).toEqual({
      kind: 'extract_review',
      entityCount: 1,
      relationshipCount: 0,
      systemCount: null,
    })
  })
})

describe('worldEntryHandoff API timestamp boundary', () => {
  const now = Date.parse('2026-09-08T02:00:02Z')
  const pending: WorldEntryPendingState = {
    kind: 'extract',
    startedAtMs: Date.parse('2026-09-08T01:59:00Z'),
    jobId: 1,
  }

  beforeEach(() => {
    vi.stubEnv('TZ', 'Asia/Shanghai')
    vi.spyOn(Date, 'now').mockReturnValue(now)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
  })

  it.each([
    '2026-09-08T02:00:00',
    '2026-09-08T02:00:00Z',
    '2026-09-08T10:00:00+08:00',
    '2026-09-07T22:00:00-04:00',
  ])('hands off a newly completed job in UTC+8: %s', (updatedAt) => {
    expect(new Date(now).getTimezoneOffset()).toBe(-480)
    const job = buildCompletedJob({
      updated_at: updatedAt,
      result: { entities_found: 1, relationships_found: 0, index_refresh_only: false },
    })
    expect(resolvePendingWorldEntryHandoffFromBootstrapJob(pending, job)).toEqual({
      kind: 'extract_review',
      entityCount: 1,
      relationshipCount: 0,
      systemCount: null,
    })
  })

  it('still rejects a truly older job with or without an explicit offset', () => {
    for (const updatedAt of ['2026-09-08T01:58:58', '2026-09-08T09:58:58+08:00']) {
      expect(resolvePendingWorldEntryHandoffFromBootstrapJob(
        pending, buildCompletedJob({ updated_at: updatedAt }),
      )).toBeNull()
    }
  })

  it('uses the same UTC parsing for the created-at fallback', () => {
    expect(resolvePendingWorldEntryHandoffFromBootstrapJob(pending, buildCompletedJob({
      updated_at: 'invalid',
      created_at: '2026-09-08T01:59:30',
    }))?.kind).toBe('extract_success')
  })

  it('preserves clock-skew allowance, pending expiry and job identity checks', () => {
    const job = buildCompletedJob({ updated_at: '2026-09-08T01:58:59' })
    expect(resolvePendingWorldEntryHandoffFromBootstrapJob(pending, job)?.kind).toBe('extract_success')
    expect(resolvePendingWorldEntryHandoffFromBootstrapJob({ ...pending, jobId: 2 }, job)).toBeNull()
    expect(resolvePendingWorldEntryHandoffFromBootstrapJob({
      ...pending, startedAtMs: now - 31 * 60_000,
    }, job)).toBeNull()
  })
})
