// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import '@/lib/uiMessagePacks/home'

import { lazy, Suspense, useEffect, useState } from 'react'
import { HeroSection } from '@/components/home/HeroSection'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'

const loadHomeDeferredSections = () => import('@/components/home/HomeDeferredSections')

const HomeDeferredSections = lazy(loadHomeDeferredSections)

function scheduleDeferredHomeSections(callback: () => void) {
  if (typeof globalThis.setTimeout !== 'function') {
    callback()
    return () => undefined
  }

  const timeoutId = globalThis.setTimeout(callback, 1)
  return () => globalThis.clearTimeout(timeoutId)
}

function DeferredSectionsFallback() {
  return (
    <div aria-hidden="true" className="flex flex-col">
      <div className="min-h-[720px] bg-[hsl(var(--lp-surface))]" />
      <div className="min-h-[1200px] bg-card" />
      <div className="min-h-[640px] bg-[hsl(var(--lp-surface))]" />
      <div className="min-h-[560px] bg-[hsl(var(--lp-cta-via))]" />
    </div>
  )
}

type HomeProps = {
  deferBelowFold?: boolean
}

function HomeDeferredSectionsSlot() {
  return (
    <Suspense fallback={<DeferredSectionsFallback />}>
      <HomeDeferredSections />
    </Suspense>
  )
}

export function Home({ deferBelowFold = true }: HomeProps = {}) {
  const [shouldLoadDeferredSections, setShouldLoadDeferredSections] = useState(false)

  useEffect(() => {
    void trackHostedAnalyticsEvent('acquisition_landing_view')
  }, [])

  useEffect(() => {
    if (!deferBelowFold) return
    let isActive = true
    const cancelScheduledLoad = scheduleDeferredHomeSections(() => {
      void loadHomeDeferredSections().then(() => {
        if (isActive) {
          setShouldLoadDeferredSections(true)
        }
      })
    })
    return () => {
      isActive = false
      cancelScheduledLoad()
    }
  }, [deferBelowFold])

  return (
    <div className="relative flex flex-col">
      <HeroSection />
      {!deferBelowFold ? (
        <HomeDeferredSectionsSlot />
      ) : shouldLoadDeferredSections ? (
        <HomeDeferredSectionsSlot />
      ) : (
        <DeferredSectionsFallback />
      )}
    </div>
  )
}

export default Home
