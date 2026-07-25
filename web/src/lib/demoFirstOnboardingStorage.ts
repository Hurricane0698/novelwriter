const KEY_PREFIX = 'novwr_demo_first_onboarding_dismissed_'

export const DEMO_FIRST_ONBOARDING_STEPS = ['chapter', 'atlas', 'write', 'copilot'] as const

export type DemoFirstOnboardingStep = (typeof DEMO_FIRST_ONBOARDING_STEPS)[number]
export type DemoFirstOnboardingStatus = 'not_started' | 'in_progress' | 'completed' | 'skipped'

export interface DemoFirstWritingOnboardingState {
  version: 2
  status: DemoFirstOnboardingStatus
  visited: Record<DemoFirstOnboardingStep, boolean>
}

const DEFAULT_VISITED: Record<DemoFirstOnboardingStep, boolean> = {
  chapter: false,
  atlas: false,
  write: false,
  copilot: false,
}

function demoFirstOnboardingDismissKey(novelId: number, createdAt?: string | null): string | null {
  if (!Number.isFinite(novelId) || novelId <= 0) return null
  const created = String(createdAt ?? '').trim()
  if (!created) return null
  return `${KEY_PREFIX}${novelId}_${created}`
}

function createDefaultState(): DemoFirstWritingOnboardingState {
  return {
    version: 2,
    status: 'not_started',
    visited: { ...DEFAULT_VISITED },
  }
}

function countVisitedInternal(visited: Record<DemoFirstOnboardingStep, boolean>): number {
  return DEMO_FIRST_ONBOARDING_STEPS.filter((step) => visited[step]).length
}

function normalizeVisited(
  visited: Partial<Record<DemoFirstOnboardingStep, unknown>> | null | undefined,
): Record<DemoFirstOnboardingStep, boolean> {
  return {
    chapter: Boolean(visited?.chapter),
    atlas: Boolean(visited?.atlas),
    write: Boolean(visited?.write),
    copilot: Boolean(visited?.copilot),
  }
}

function readStoredState(key: string): DemoFirstWritingOnboardingState {
  const raw = localStorage.getItem(key)
  if (!raw) return createDefaultState()

  // Legacy contract: the old one-bit dismissal key hid the guide too aggressively,
  // so intentionally reset old values into the new progress-aware flow.
  if (raw === '1') {
    try {
      localStorage.removeItem(key)
    } catch {
      // ignore
    }
    return createDefaultState()
  }

  try {
    const parsed = JSON.parse(raw) as {
      version?: number
      status?: DemoFirstOnboardingStatus
      visited?: Partial<Record<DemoFirstOnboardingStep, unknown>>
    }
    const visited = normalizeVisited(parsed?.visited)
    const visitedCount = countVisitedInternal(visited)
    const allVisited = visitedCount === DEMO_FIRST_ONBOARDING_STEPS.length
    const status = parsed?.status

    return {
      version: 2,
      status: allVisited
        ? 'completed'
        : status === 'skipped'
          ? 'skipped'
          : visitedCount > 0
            ? 'in_progress'
            : 'not_started',
      visited,
    }
  } catch {
    return createDefaultState()
  }
}

function writeState(key: string, state: DemoFirstWritingOnboardingState): void {
  localStorage.setItem(key, JSON.stringify(state))
}

export function getDemoFirstWritingOnboardingState(
  novelId: number,
  createdAt?: string | null,
): DemoFirstWritingOnboardingState {
  try {
    const key = demoFirstOnboardingDismissKey(novelId, createdAt)
    if (!key) return createDefaultState()
    return readStoredState(key)
  } catch {
    return createDefaultState()
  }
}

export function countVisitedDemoFirstWritingOnboardingSteps(
  state: Pick<DemoFirstWritingOnboardingState, 'visited'>,
): number {
  return countVisitedInternal(state.visited)
}

export function markDemoFirstWritingOnboardingStepVisited(
  novelId: number,
  createdAt: string | null | undefined,
  step: DemoFirstOnboardingStep,
): DemoFirstWritingOnboardingState {
  const key = demoFirstOnboardingDismissKey(novelId, createdAt)
  const fallback = createDefaultState()
  if (!key) return fallback

  try {
    const current = readStoredState(key)
    if (current.visited[step]) return current

    const visited = {
      ...current.visited,
      [step]: true,
    }
    const visitedCount = countVisitedInternal(visited)
    const next: DemoFirstWritingOnboardingState = {
      version: 2,
      status: visitedCount === DEMO_FIRST_ONBOARDING_STEPS.length
        ? 'completed'
        : current.status === 'skipped'
          ? 'skipped'
          : 'in_progress',
      visited,
    }
    writeState(key, next)
    return next
  } catch {
    return fallback
  }
}

export function skipDemoFirstWritingOnboarding(
  novelId: number,
  createdAt?: string | null,
): DemoFirstWritingOnboardingState {
  const key = demoFirstOnboardingDismissKey(novelId, createdAt)
  const fallback = createDefaultState()
  if (!key) return fallback

  try {
    const current = readStoredState(key)
    const next: DemoFirstWritingOnboardingState = {
      version: 2,
      status: 'skipped',
      visited: current.visited,
    }
    writeState(key, next)
    return next
  } catch {
    return fallback
  }
}

export function clearDemoFirstWritingOnboardingDismissed(
  novelId: number,
  createdAt?: string | null,
): void {
  const key = demoFirstOnboardingDismissKey(novelId, createdAt)
  if (!key) return
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore
  }
}
