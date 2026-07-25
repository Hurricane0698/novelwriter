import type { DemoFirstWritingOnboardingState } from '@/lib/demoFirstOnboardingStorage'

interface ResolveStudioDemoGuideVisibilityArgs {
  demoGuideSearchParam: string | null
  manualForceOpenDemoGuide: boolean
  showWorldOnboarding: boolean
  isDemoNovel: boolean
  demoGuideState: Pick<DemoFirstWritingOnboardingState, 'status'>
}

export interface StudioDemoGuideVisibilityState {
  forceOpenDemoGuide: boolean
  showDemoGuideExpanded: boolean
  showDemoGuideReopen: boolean
}

export function resolveStudioDemoGuideVisibility({
  demoGuideSearchParam,
  manualForceOpenDemoGuide,
  showWorldOnboarding,
  isDemoNovel,
  demoGuideState,
}: ResolveStudioDemoGuideVisibilityArgs): StudioDemoGuideVisibilityState {
  const forceOpenDemoGuide = demoGuideSearchParam === 'open' || manualForceOpenDemoGuide
  const isDemoGuideDismissed = demoGuideState.status === 'completed' || demoGuideState.status === 'skipped'
  const showDemoGuideExpanded = !showWorldOnboarding && isDemoNovel && (forceOpenDemoGuide || !isDemoGuideDismissed)
  const showDemoGuideReopen = !showWorldOnboarding && isDemoNovel && !showDemoGuideExpanded

  return {
    forceOpenDemoGuide,
    showDemoGuideExpanded,
    showDemoGuideReopen,
  }
}
