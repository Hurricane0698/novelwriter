import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useDemoFirstGuideStorageState } from '@/hooks/novel/useDemoFirstGuideStorageState'

describe('useDemoFirstGuideStorageState', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reads demo-guide progress from the created-at-scoped storage key', () => {
    localStorage.setItem(
      'novwr_demo_first_onboarding_dismissed_7_2026-03-01T00:00:00Z',
      JSON.stringify({
        version: 2,
        status: 'completed',
        visited: {
          chapter: true,
          atlas: true,
          write: true,
          copilot: true,
        },
      }),
    )

    const { result, rerender } = renderHook(
      ({ createdAt }) => useDemoFirstGuideStorageState({ novelId: 7, createdAt }),
      { initialProps: { createdAt: '2026-03-01T00:00:00Z' } },
    )

    expect(result.current.demoGuideState.status).toBe('completed')

    rerender({ createdAt: '2026-03-02T00:00:00Z' })

    expect(result.current.demoGuideState.status).toBe('not_started')
  })

  it('scopes the manual reopen flag by the same storage identity', () => {
    const { result, rerender } = renderHook(
      ({ createdAt }) => useDemoFirstGuideStorageState({ novelId: 7, createdAt }),
      { initialProps: { createdAt: '2026-03-01T00:00:00Z' } },
    )

    act(() => {
      result.current.openManualDemoGuide()
    })

    expect(result.current.manualForceOpenDemoGuide).toBe(true)

    rerender({ createdAt: '2026-03-02T00:00:00Z' })

    expect(result.current.manualForceOpenDemoGuide).toBe(false)
  })
})
