const KEY_PREFIX = 'novwr_world_onboarding_dismissed_'

export function worldOnboardingDismissKey(novelId: number, createdAt?: string | null): string | null {
  if (!Number.isFinite(novelId) || novelId <= 0) return null
  const created = String(createdAt ?? '').trim()
  if (!created) return null
  return `${KEY_PREFIX}${novelId}_${created}`
}

export function worldOnboardingLegacyDismissKey(novelId: number): string | null {
  if (!Number.isFinite(novelId) || novelId <= 0) return null
  return `${KEY_PREFIX}${novelId}`
}

export function isWorldOnboardingDismissed(novelId: number, createdAt?: string | null): boolean {
  try {
    const key = worldOnboardingDismissKey(novelId, createdAt)
    if (key && localStorage.getItem(key) === '1') return true

    const legacyKey = worldOnboardingLegacyDismissKey(novelId)
    if (!legacyKey) return false
    if (localStorage.getItem(legacyKey) !== '1') return false

    // Back-compat: migrate legacy -> new (when possible) to avoid collisions if ids are reused.
    if (key) {
      try {
        localStorage.setItem(key, '1')
      } catch {
        // ignore
      }
      try {
        localStorage.removeItem(legacyKey)
      } catch {
        // ignore
      }
    }
    return true
  } catch {
    return false
  }
}

export function dismissWorldOnboarding(novelId: number, createdAt?: string | null): void {
  const key = worldOnboardingDismissKey(novelId, createdAt)
  try {
    if (key) {
      localStorage.setItem(key, '1')
      const legacyKey = worldOnboardingLegacyDismissKey(novelId)
      if (legacyKey) localStorage.removeItem(legacyKey)
      return
    }

    const legacyKey = worldOnboardingLegacyDismissKey(novelId)
    if (!legacyKey) return
    localStorage.setItem(legacyKey, '1')
  } catch {
    // ignore
  }
}

export function clearWorldOnboardingDismissed(novelId: number, createdAt?: string | null): void {
  const keys = [
    worldOnboardingDismissKey(novelId, createdAt),
    worldOnboardingLegacyDismissKey(novelId),
  ].filter(Boolean) as string[]
  for (const k of keys) {
    try {
      localStorage.removeItem(k)
    } catch {
      // ignore
    }
  }
}
