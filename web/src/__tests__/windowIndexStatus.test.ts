import { describe, expect, it } from 'vitest'
import '@/lib/uiMessagePacks/novel'
import {
  getWindowIndexBootstrapStatusMeta,
  getWindowIndexPollingInterval,
  isWindowIndexRebuilding,
} from '@/lib/windowIndexStatus'
import type { WindowIndexState } from '@/types/api'

describe('windowIndexStatus', () => {
  it('treats accepting readiness as preparing without fallback', () => {
    const state: WindowIndexState = {
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
        size_tier: null,
        source_bytes: 128,
        source_chars: null,
        chapter_count: null,
        requested_language: null,
        resolved_language: null,
        auto_index_plan: null,
        bootstrap_plan: null,
        readiness_mode: null,
        error_code: null,
        error: null,
      },
      job: null,
    }

    expect(isWindowIndexRebuilding(state)).toBe(true)
    expect(getWindowIndexPollingInterval(state)).toBe(2000)
    expect(getWindowIndexBootstrapStatusMeta(state, 'zh')).toEqual({
      text: '正在准备全书内容',
      tone: 'muted',
      requiresFallback: false,
    })
  })

  it('does not infer healthy rebuilding from raw job rows when readiness is degraded', () => {
    const state: WindowIndexState = {
      status: 'missing',
      revision: 2,
      built_revision: null,
      error: null,
      readiness: 'degraded_ready',
      capabilities: {
        chapters_available: true,
        whole_book_index_available: false,
        bootstrap_available: true,
        recent_fallback_only: true,
      },
      ingest: {
        status: 'running',
        stage: 'persisting',
        size_tier: 'xlarge',
        source_bytes: 128,
        source_chars: 256,
        chapter_count: 2,
        requested_language: 'zh',
        resolved_language: 'zh',
        auto_index_plan: 'skip_auto',
        bootstrap_plan: 'manual_only',
        readiness_mode: 'degraded_target',
        error_code: null,
        error: null,
      },
      job: {
        status: 'running',
        target_revision: 2,
        completed_revision: null,
        error: null,
      },
    }

    expect(isWindowIndexRebuilding(state)).toBe(false)
    expect(getWindowIndexPollingInterval(state)).toBe(false)
    expect(getWindowIndexBootstrapStatusMeta(state, 'zh')).toEqual({
      text: '还在准备全书内容',
      tone: 'warning',
      requiresFallback: true,
    })
  })

  it('treats terminal ingest failure as stopped without fallback content', () => {
    const state: WindowIndexState = {
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
        source_bytes: 128,
        source_chars: null,
        chapter_count: null,
        requested_language: null,
        resolved_language: null,
        auto_index_plan: null,
        bootstrap_plan: null,
        readiness_mode: null,
        error_code: 'markdown_structure_invalid',
        error: 'sanitized diagnostic',
      },
      job: null,
    }

    expect(isWindowIndexRebuilding(state)).toBe(false)
    expect(getWindowIndexPollingInterval(state)).toBe(false)
    expect(getWindowIndexBootstrapStatusMeta(state, 'zh')).toEqual({
      text: '全书检索暂不可用',
      tone: 'warning',
      requiresFallback: false,
    })
  })
})
