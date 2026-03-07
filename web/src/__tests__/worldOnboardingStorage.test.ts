import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  dismissWorldOnboarding,
  isWorldOnboardingDismissed,
  worldOnboardingDismissKey,
  worldOnboardingLegacyDismissKey,
} from '@/lib/worldOnboardingStorage'

describe('worldOnboardingStorage', () => {
  const novelId = 1
  const createdAt = '2026-03-04T00:00:00Z'

  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('uses a createdAt-scoped key when available', () => {
    expect(worldOnboardingDismissKey(novelId, createdAt)).toBe(
      'novwr_world_onboarding_dismissed_1_2026-03-04T00:00:00Z',
    )
  })

  it('falls back to legacy key when createdAt is missing', () => {
    dismissWorldOnboarding(novelId, null)
    const legacyKey = worldOnboardingLegacyDismissKey(novelId)
    expect(legacyKey).toBe('novwr_world_onboarding_dismissed_1')
    expect(localStorage.getItem(legacyKey!)).toBe('1')
  })

  it('treats legacy dismissal as dismissed and migrates to the new key when possible', () => {
    const legacyKey = worldOnboardingLegacyDismissKey(novelId)!
    localStorage.setItem(legacyKey, '1')

    expect(isWorldOnboardingDismissed(novelId, createdAt)).toBe(true)

    const key = worldOnboardingDismissKey(novelId, createdAt)!
    expect(localStorage.getItem(key)).toBe('1')
    expect(localStorage.getItem(legacyKey)).toBeNull()
  })

  it('returns false when localStorage.getItem throws (SecurityError)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(isWorldOnboardingDismissed(novelId, createdAt)).toBe(false)
  })
})

