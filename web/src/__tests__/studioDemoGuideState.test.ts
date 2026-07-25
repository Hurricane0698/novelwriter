import { describe, expect, it } from 'vitest'
import { resolveStudioDemoGuideVisibility } from '@/hooks/novel/studioDemoGuideState'

describe('studioDemoGuideState', () => {
  it('collapses a completed demo guide into the reopen state by default', () => {
    const visibility = resolveStudioDemoGuideVisibility({
      demoGuideSearchParam: null,
      manualForceOpenDemoGuide: false,
      showWorldOnboarding: false,
      isDemoNovel: true,
      demoGuideState: { status: 'completed' },
    })

    expect(visibility).toEqual({
      forceOpenDemoGuide: false,
      showDemoGuideExpanded: false,
      showDemoGuideReopen: true,
    })
  })

  it('forces the guide open from the URL even after completion', () => {
    const visibility = resolveStudioDemoGuideVisibility({
      demoGuideSearchParam: 'open',
      manualForceOpenDemoGuide: false,
      showWorldOnboarding: false,
      isDemoNovel: true,
      demoGuideState: { status: 'completed' },
    })

    expect(visibility).toEqual({
      forceOpenDemoGuide: true,
      showDemoGuideExpanded: true,
      showDemoGuideReopen: false,
    })
  })

  it('never shows the demo guide while world onboarding owns the entry stage', () => {
    const visibility = resolveStudioDemoGuideVisibility({
      demoGuideSearchParam: 'open',
      manualForceOpenDemoGuide: true,
      showWorldOnboarding: true,
      isDemoNovel: true,
      demoGuideState: { status: 'in_progress' },
    })

    expect(visibility).toEqual({
      forceOpenDemoGuide: true,
      showDemoGuideExpanded: false,
      showDemoGuideReopen: false,
    })
  })
})
