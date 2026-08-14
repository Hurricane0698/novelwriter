import { describe, expect, it, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useStudioArtifactState } from '@/hooks/novel/useStudioArtifactState'
import type { ContinueDebugSummary } from '@/types/api'

const mockReadGenerationResultsDebug = vi.fn()

vi.mock('@/lib/generationResultsDebugStorage', () => ({
  readGenerationResultsDebug: (...args: unknown[]) => mockReadGenerationResultsDebug(...args),
}))

function buildDebugSummary(partial?: Partial<ContinueDebugSummary>): ContinueDebugSummary {
  return {
    context_chapters: 3,
    injected_systems: [],
    injected_entities: [],
    injected_relationships: [],
    injected_context_summaries: [],
    relevant_entity_ids: [],
    ambiguous_keywords_disabled: [],
    drift_warnings: [],
    prose_warnings: [],
    ...partial,
  }
}

describe('useStudioArtifactState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('preserves persisted results provenance and active injection-summary panel across stage hops', () => {
    const navigate = vi.fn()
    const persistedDebug = buildDebugSummary({ injected_systems: ['世界规则'] })
    mockReadGenerationResultsDebug.mockReturnValue(persistedDebug)

    const { result } = renderHook(() => useStudioArtifactState({
      novelId: 7,
      activeStage: 'results',
      activeChapterNum: 3,
      routeState: {
        entityId: null,
        systemId: null,
        reviewKind: null,
      },
      location: {
        key: 'loc-results',
        pathname: '/novel/7',
        search: '?stage=results&chapter=3&continuations=0:101&total_variants=1&artifactPanel=injection_summary&summaryCategory=systems',
        state: null,
      },
      searchParams: new URLSearchParams('stage=results&chapter=3&continuations=0:101&total_variants=1&artifactPanel=injection_summary&summaryCategory=systems'),
      navigate,
    }))

    expect(result.current.hasResultsContext).toBe(true)
    expect(result.current.resultsDebug).toEqual(persistedDebug)
    expect(result.current.showInjectionSummaryRail).toBe(true)
    expect(result.current.effectiveResultsProvenance).toEqual({
      chapterNum: 3,
      continuations: '0:101',
      totalVariants: 1,
    })

    const nextSearchParams = result.current.applyActiveArtifactContextSearchParams(
      new URLSearchParams('stage=entity&entity=9&chapter=3'),
    )
    expect(nextSearchParams.get('resultsChapter')).toBe('3')
    expect(nextSearchParams.get('resultsContinuations')).toBe('0:101')
    expect(nextSearchParams.get('resultsTotalVariants')).toBe('1')
    expect(nextSearchParams.get('artifactPanel')).toBe('injection_summary')
    expect(nextSearchParams.get('summaryCategory')).toBe('systems')
  })

  it('keeps ephemeral results debug in local hook state before continuations are persisted', () => {
    const navigate = vi.fn()
    const initialDebug = buildDebugSummary({ injected_entities: ['旧实体'] })
    const liveDebug = buildDebugSummary({ injected_entities: ['新实体'] })

    const { result } = renderHook(() => useStudioArtifactState({
      novelId: 7,
      activeStage: 'results',
      activeChapterNum: 3,
      routeState: {
        entityId: null,
        systemId: null,
        reviewKind: null,
      },
      location: {
        key: 'loc-ephemeral',
        pathname: '/novel/7',
        search: '?stage=results&chapter=3',
        state: {
          novelId: 7,
          streamParams: { num_versions: 1 },
          studioResultsDebug: initialDebug,
        },
      },
      searchParams: new URLSearchParams('stage=results&chapter=3'),
      navigate,
    }))

    expect(result.current.currentResultsDebugKey).toBe('ephemeral:loc-ephemeral')
    expect(result.current.resultsDebug).toEqual(initialDebug)

    act(() => {
      result.current.handleResultsDebugChange(liveDebug)
    })

    expect(result.current.resultsDebug).toEqual(liveDebug)
  })
})
