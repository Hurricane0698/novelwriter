import { describe, expect, it, vi } from 'vitest'
import { resolveStudioPreparationGate } from '@/hooks/novel/studioOnboardingPreparation'
import type { BootstrapJobResponse, Novel } from '@/types/api'

function buildNovel(partial?: Partial<Novel>): Novel {
  return {
    id: 7,
    title: '测试小说',
    author: '作者',
    language: 'zh',
    content_format: 'plain_text',
    total_chapters: 3,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    ...partial,
  }
}

function buildBootstrapJob(partial?: Partial<BootstrapJobResponse>): BootstrapJobResponse {
  return {
    job_id: 11,
    novel_id: 7,
    mode: 'initial',
    initialized: false,
    status: 'pending',
    progress: {
      step: 0,
      detail: 'queued',
    },
    result: {
      entities_found: 0,
      relationships_found: 0,
      index_refresh_only: false,
    },
    error: null,
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
    ...partial,
  }
}

function t(key: string) {
  return key
}

describe('studioOnboardingPreparation', () => {
  it('returns the ingest preparation gate before chapters are available', () => {
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'missing',
          revision: 0,
          built_revision: null,
          error: null,
          readiness: 'accepting',
          capabilities: {
            chapters_available: false,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'queued',
            stage: 'accepted',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: null,
            chapter_count: null,
            requested_language: 'zh',
            resolved_language: null,
            auto_index_plan: null,
            bootstrap_plan: null,
            readiness_mode: null,
            error: null,
            error_code: null,
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: null,
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.title',
      description: 'studio.preparation.uploadDescription',
      detail: 'studio.preparation.stage.accepted',
      error: null,
    })
  })

  it('returns the failed bootstrap gate with retry and defer actions', () => {
    const onRetryBootstrap = vi.fn()
    const onDeferBootstrap = vi.fn()

    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: null,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: buildBootstrapJob({ status: 'failed', error: 'bootstrap crashed' }),
      bootstrapError: 'mapped failure',
      onRetryBootstrap,
      onDeferBootstrap,
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).not.toBeNull()
    expect(gate).toMatchObject({
      title: 'studio.preparation.failedTitle',
      description: 'studio.preparation.failedDescription',
      error: 'mapped failure',
      primaryActionLabel: 'studio.preparation.retry',
      secondaryActionLabel: 'studio.preparation.defer',
    })

    gate?.onPrimaryAction?.()
    gate?.onSecondaryAction?.()

    expect(onRetryBootstrap).toHaveBeenCalledTimes(1)
    expect(onDeferBootstrap).toHaveBeenCalledTimes(1)
  })

  it('surfaces retry/defer actions on the preparation gate after initial extraction fails', () => {
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'normal',
            source_bytes: 128,
            source_chars: 64,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'immediate',
            bootstrap_plan: 'immediate',
            readiness_mode: 'full_target',
            error: null,
            error_code: null,
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: buildBootstrapJob({
        status: 'failed',
        mode: 'initial',
        initialized: false,
        error: 'boom',
      }),
      bootstrapError: 'boom',
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.failedTitle',
      description: 'studio.preparation.failedDescription',
      error: 'boom',
      primaryActionLabel: 'studio.preparation.retry',
      secondaryActionLabel: 'studio.preparation.defer',
    })
  })

  it('keeps the preparation gate up while deferred auto-bootstrap is waiting on whole-book index', () => {
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'missing',
          revision: 2,
          built_revision: null,
          error: null,
          readiness: 'processing',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: true,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: 2048,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'deferred',
            bootstrap_plan: 'defer_until_index',
            readiness_mode: 'degraded_target',
            error: null,
            error_code: null,
          },
          job: {
            status: 'running',
            target_revision: 2,
            completed_revision: null,
            error: null,
            created_at: null,
            started_at: null,
            finished_at: null,
            metrics: null,
          },
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: null,
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.title',
      description: 'studio.preparation.bootstrapDescription',
      detail: 'worldModel.windowIndex.bootstrap.organizingChapters',
      error: null,
    })
  })

  it('keeps the preparation gate up after initial bootstrap completes until world queries refresh', () => {
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: 2048,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'deferred',
            bootstrap_plan: 'defer_until_index',
            readiness_mode: 'degraded_target',
            error: null,
            error_code: null,
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: buildBootstrapJob({
        status: 'completed',
        result: {
          entities_found: 28,
          relationships_found: 22,
          index_refresh_only: false,
        },
      }),
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.title',
      description: 'studio.preparation.bootstrapDescription',
      detail: 'worldModel.common.processing',
      error: null,
    })
  })

  it('drops the preparation gate after initial bootstrap completes with no extracted world data', () => {
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'completed',
            stage: 'completed',
            size_tier: 'large',
            source_bytes: 1024,
            source_chars: 2048,
            chapter_count: 2,
            requested_language: 'zh',
            resolved_language: 'zh',
            auto_index_plan: 'deferred',
            bootstrap_plan: 'defer_until_index',
            readiness_mode: 'degraded_target',
            error: null,
            error_code: null,
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: buildBootstrapJob({
        status: 'completed',
        initialized: true,
        result: {
          entities_found: 0,
          relationships_found: 0,
          index_refresh_only: false,
        },
      }),
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest: vi.fn(),
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toBeNull()
  })

  it('returns source-fix guidance without a retry action for invalid Markdown', () => {
    const onRetryIngest = vi.fn()
    const onReturnToLibrary = vi.fn()
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        content_format: 'markdown',
        window_index: {
          status: 'missing',
          revision: 0,
          built_revision: null,
          error: null,
          readiness: 'failed_terminal',
          capabilities: {
            chapters_available: false,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'failed',
            stage: 'failed',
            size_tier: 'normal',
            source_bytes: 64,
            source_chars: null,
            chapter_count: null,
            requested_language: 'auto',
            resolved_language: null,
            auto_index_plan: null,
            bootstrap_plan: null,
            readiness_mode: null,
            error: 'Markdown structure is invalid',
            error_code: 'markdown_structure_invalid',
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: null,
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest,
      onReturnToLibrary,
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.ingestNeedsFixTitle',
      error: 'studio.preparation.markdownRepair',
      primaryActionLabel: 'studio.preparation.returnLibrary',
    })
    expect(gate).not.toHaveProperty('secondaryActionLabel')
    gate?.onPrimaryAction?.()
    expect(onReturnToLibrary).toHaveBeenCalledTimes(1)
    expect(onRetryIngest).not.toHaveBeenCalled()
  })

  it('only exposes ingest retry for internal failures', () => {
    const onRetryIngest = vi.fn()
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'missing',
          revision: 0,
          built_revision: null,
          error: null,
          readiness: 'failed_retryable',
          capabilities: {
            chapters_available: false,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'failed',
            stage: 'failed',
            size_tier: 'normal',
            source_bytes: 64,
            source_chars: null,
            chapter_count: null,
            requested_language: 'auto',
            resolved_language: null,
            auto_index_plan: null,
            bootstrap_plan: null,
            readiness_mode: null,
            error: 'Novel ingest failed',
            error_code: 'ingest_internal_error',
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: null,
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest,
      onReturnToLibrary: vi.fn(),
    })

    expect(gate).toMatchObject({
      primaryActionLabel: 'studio.preparation.retryImport',
      secondaryActionLabel: 'studio.preparation.returnLibrary',
    })
    gate?.onPrimaryAction?.()
    expect(onRetryIngest).toHaveBeenCalledTimes(1)
  })

  it('keeps a failed ingest without an error code terminal and non-retryable', () => {
    const onRetryIngest = vi.fn()
    const onReturnToLibrary = vi.fn()
    const gate = resolveStudioPreparationGate({
      t,
      novelWindowIndex: buildNovel({
        window_index: {
          status: 'missing',
          revision: 0,
          built_revision: null,
          error: null,
          readiness: 'failed_terminal',
          capabilities: {
            chapters_available: false,
            whole_book_index_available: false,
            bootstrap_available: false,
            recent_fallback_only: false,
          },
          ingest: {
            status: 'failed',
            stage: 'failed',
            size_tier: null,
            source_bytes: 64,
            source_chars: null,
            chapter_count: null,
            requested_language: null,
            resolved_language: null,
            auto_index_plan: null,
            bootstrap_plan: null,
            readiness_mode: null,
            error_code: null,
            error: 'sanitized diagnostic',
          },
          job: null,
        },
      }).window_index,
      worldLoading: false,
      worldOnboardingDismissed: false,
      worldEmpty: true,
      bootstrapTriggerPending: false,
      bootstrapJob: null,
      bootstrapError: null,
      onRetryBootstrap: vi.fn(),
      onDeferBootstrap: vi.fn(),
      onRetryIngest,
      onReturnToLibrary,
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.ingestNeedsFixTitle',
      error: null,
      primaryActionLabel: 'studio.preparation.returnLibrary',
    })
    expect(gate).not.toHaveProperty('secondaryActionLabel')
    gate?.onPrimaryAction?.()
    expect(onReturnToLibrary).toHaveBeenCalledTimes(1)
    expect(onRetryIngest).not.toHaveBeenCalled()
  })
})
