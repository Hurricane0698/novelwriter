// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { homeNarrativeActs } from '@/components/home/homeContent'
import { StageShell } from '@/components/home/StageShell'
import { ScreenshotStageAsset, ScreenshotExpandLink } from '@/components/home/ScreenshotStageAsset'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { preloadHomeProductStageScreenshots } from '@/components/home/homeScreenshotAssets'
import type { NarrativeActs } from '@/components/home/useNarrativeScroll'

type ProductStageProps = {
  activeAct: NarrativeActs
  prefersReducedMotion: boolean
}

export function ProductStage({ activeAct, prefersReducedMotion }: ProductStageProps) {
  const { t } = useUiLocale()
  useEffect(() => {
    void preloadHomeProductStageScreenshots()
  }, [])
  const activeSceneId = homeNarrativeActs[activeAct].sceneId
  const activeScene = sceneManifest[activeSceneId]

  return (
    <div className="relative h-full overflow-hidden rounded-[20px]">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div key={activeAct} className="absolute inset-0"
          initial={prefersReducedMotion ? false : { opacity: 0, y: 80, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -64, scale: prefersReducedMotion ? 1 : 0.98 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.46, ease: [0.22, 1, 0.36, 1] }}>
          <StageShell className="h-full" bodyClassName="relative min-h-0 flex-1 overflow-hidden" label={t(activeScene.windowLabelKey)}
            headerAction={<ScreenshotExpandLink src={activeScene.screenshot} alt={t(activeScene.labelKey)} />}>
            <ScreenshotStageAsset src={activeScene.screenshot} alt={t(activeScene.labelKey)} mobilePosition={activeScene.mobilePosition} mobileScale={activeScene.mobileScale} />
          </StageShell>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
