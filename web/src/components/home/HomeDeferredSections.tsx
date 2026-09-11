// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { InjectionSection } from '@/components/home/InjectionSection'
import { StickyNarrative } from '@/components/home/StickyNarrative'
import { SurfaceTabs } from '@/components/home/SurfaceTabs'
import { ClosingCTA } from '@/components/home/ClosingCTA'
import { SiteFooter } from '@/components/layout/SiteFooter'

export function HomeDeferredSections() {
  return (
    <>
      <InjectionSection />
      <StickyNarrative />
      <SurfaceTabs />
      <ClosingCTA />
      <SiteFooter />
    </>
  )
}

export default HomeDeferredSections
