import { describe, expect, it } from 'vitest'
import { resolveStudioPreparationGate } from '@/hooks/novel/studioOnboardingPreparation'
import type { Novel } from '@/types/api'

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
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.title',
      description: 'studio.preparation.uploadDescription',
      detail: 'studio.preparation.stage.accepted',
      error: null,
    })
  })

  it('returns source-fix guidance without a retry action for invalid Markdown', () => {
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
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.ingestNeedsFixTitle',
      error: 'studio.preparation.markdownRepair',
      primaryActionLabel: 'studio.preparation.returnLibrary',
    })
    expect(gate).not.toHaveProperty('secondaryActionLabel')
  })

  it('only exposes ingest retry for internal failures', () => {
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
    })

    expect(gate).toMatchObject({
      primaryActionLabel: 'studio.preparation.retryImport',
      secondaryActionLabel: 'studio.preparation.returnLibrary',
    })
  })

  it('keeps a failed ingest without an error code terminal and non-retryable', () => {
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
    })

    expect(gate).toMatchObject({
      title: 'studio.preparation.ingestNeedsFixTitle',
      error: null,
      primaryActionLabel: 'studio.preparation.returnLibrary',
    })
    expect(gate).not.toHaveProperty('secondaryActionLabel')
  })
})
