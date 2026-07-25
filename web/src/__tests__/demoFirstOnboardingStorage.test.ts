import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEMO_FIRST_ONBOARDING_STEPS,
  countVisitedDemoFirstWritingOnboardingSteps,
  getDemoFirstWritingOnboardingState,
  markDemoFirstWritingOnboardingStepVisited,
  skipDemoFirstWritingOnboarding,
} from '@/lib/demoFirstOnboardingStorage'

describe('demoFirstOnboardingStorage', () => {
  const novelId = 7
  const createdAt = '2026-03-04T00:00:00Z'
  const storageKey = `novwr_demo_first_onboarding_dismissed_${novelId}_${createdAt}`

  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts with a not-started progress state', () => {
    const state = getDemoFirstWritingOnboardingState(novelId, createdAt)

    expect(state.status).toBe('not_started')
    expect(countVisitedDemoFirstWritingOnboardingSteps(state)).toBe(0)
    expect(state.visited).toEqual({
      chapter: false,
      atlas: false,
      write: false,
      copilot: false,
    })
  })

  it('tracks visited steps and becomes completed after the full loop', () => {
    let state = markDemoFirstWritingOnboardingStepVisited(novelId, createdAt, 'chapter')
    expect(state.status).toBe('in_progress')
    expect(state.visited.chapter).toBe(true)

    for (const step of DEMO_FIRST_ONBOARDING_STEPS.filter((item) => item !== 'chapter')) {
      state = markDemoFirstWritingOnboardingStepVisited(novelId, createdAt, step)
    }

    expect(state.status).toBe('completed')
    expect(countVisitedDemoFirstWritingOnboardingSteps(state)).toBe(4)
    expect(getDemoFirstWritingOnboardingState(novelId, createdAt).status).toBe('completed')
  })

  it('marks skip explicitly without erasing partial progress', () => {
    markDemoFirstWritingOnboardingStepVisited(novelId, createdAt, 'chapter')

    const skipped = skipDemoFirstWritingOnboarding(novelId, createdAt)

    expect(skipped.status).toBe('skipped')
    expect(skipped.visited.chapter).toBe(true)
    expect(getDemoFirstWritingOnboardingState(novelId, createdAt).status).toBe('skipped')
  })

  it('resets the old one-bit dismissal value into the new progress-aware flow', () => {
    localStorage.setItem(storageKey, '1')

    const state = getDemoFirstWritingOnboardingState(novelId, createdAt)

    expect(state.status).toBe('not_started')
    expect(localStorage.getItem(storageKey)).toBeNull()
  })

  it('falls back to a safe default state when localStorage access throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(getDemoFirstWritingOnboardingState(novelId, createdAt).status).toBe('not_started')
  })
})
