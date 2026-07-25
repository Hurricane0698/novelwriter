import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getDemoFirstWritingOnboardingState,
  markDemoFirstWritingOnboardingStepVisited,
  skipDemoFirstWritingOnboarding,
  type DemoFirstOnboardingStep,
  type DemoFirstWritingOnboardingState,
} from '@/lib/demoFirstOnboardingStorage'

export interface DemoFirstGuideStateTransition {
  previous: DemoFirstWritingOnboardingState
  next: DemoFirstWritingOnboardingState
}

interface UseDemoFirstGuideStorageStateArgs {
  novelId: number
  createdAt?: string | null
}

export function useDemoFirstGuideStorageState({
  novelId,
  createdAt,
}: UseDemoFirstGuideStorageStateArgs) {
  const demoGuideStorageKey = `${novelId}:${createdAt ?? ''}`
  const [demoGuideStateStore, setDemoGuideStateStore] = useState<{
    key: string
    value: DemoFirstWritingOnboardingState
  }>(() => ({
    key: `${novelId}:`,
    value: getDemoFirstWritingOnboardingState(novelId),
  }))
  const demoGuideState = demoGuideStateStore.key === demoGuideStorageKey
    ? demoGuideStateStore.value
    : getDemoFirstWritingOnboardingState(novelId, createdAt)
  const demoGuideStateRef = useRef(demoGuideState)

  const [manualDemoGuideOpenStore, setManualDemoGuideOpenStore] = useState<{
    key: string
    value: boolean
  }>({
    key: `${novelId}:`,
    value: false,
  })
  const manualForceOpenDemoGuide = manualDemoGuideOpenStore.key === demoGuideStorageKey
    ? manualDemoGuideOpenStore.value
    : false

  useEffect(() => {
    demoGuideStateRef.current = demoGuideState
  }, [demoGuideState])

  const storeDemoGuideState = useCallback((next: DemoFirstWritingOnboardingState) => {
    demoGuideStateRef.current = next
    setDemoGuideStateStore({
      key: demoGuideStorageKey,
      value: next,
    })
  }, [demoGuideStorageKey])

  const markStepVisited = useCallback((step: DemoFirstOnboardingStep): DemoFirstGuideStateTransition => {
    const previous = demoGuideStateRef.current
    const next = markDemoFirstWritingOnboardingStepVisited(novelId, createdAt, step)
    storeDemoGuideState(next)
    return { previous, next }
  }, [createdAt, novelId, storeDemoGuideState])

  const skipDemoGuide = useCallback((): DemoFirstGuideStateTransition => {
    const previous = demoGuideStateRef.current
    const next = skipDemoFirstWritingOnboarding(novelId, createdAt)
    storeDemoGuideState(next)
    return { previous, next }
  }, [createdAt, novelId, storeDemoGuideState])

  const openManualDemoGuide = useCallback(() => {
    setManualDemoGuideOpenStore({
      key: demoGuideStorageKey,
      value: true,
    })
  }, [demoGuideStorageKey])

  const closeManualDemoGuide = useCallback(() => {
    setManualDemoGuideOpenStore({
      key: demoGuideStorageKey,
      value: false,
    })
  }, [demoGuideStorageKey])

  return {
    demoGuideStorageKey,
    demoGuideState,
    manualForceOpenDemoGuide,
    markStepVisited,
    skipDemoGuide,
    openManualDemoGuide,
    closeManualDemoGuide,
  }
}
