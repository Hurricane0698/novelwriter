// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { motion } from 'framer-motion'
import { StageShell } from '@/components/home/StageShell'
import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { useUiLocale } from '@/contexts/UiLocaleContext'

/**
 * Hero visual — single clean product screenshot with depth layers.
 *
 * Design intent: ONE dominant screenshot (Studio) with clear framing,
 * no overlapping text chips that cause visual clutter. A smaller Atlas
 * card peeks from below-right to hint at depth without competing.
 */
export function HeroVisual() {
  const { t } = useUiLocale()
  const studio = homeScreenshotAssets.studioWorkspace
  const atlas = homeScreenshotAssets.atlasWorkspace

  return (
    <div className="relative mx-auto w-full max-w-[680px] lg:mx-0">
      {/* Main product screenshot — clean, prominent */}
      <motion.div
        initial={{ opacity: 0, y: 32, rotateX: 6 }}
        animate={{ opacity: 1, y: 0, rotateX: 0 }}
        transition={{ duration: 0.9, delay: 0.15, ease: 'easeOut' }}
        style={{ transformPerspective: 1200 }}
      >
        <StageShell
          accentHex={sceneManifest.continuation.accentHex}
          label={t(sceneManifest.continuation.windowLabelKey)}
        >
          <div className="relative h-[340px] sm:h-[420px]">
            <ScreenshotStageAsset
              src={studio}
              alt={t(sceneManifest.continuation.labelKey)}
              imageClassName="object-contain bg-white"
              objectPosition="center center"
              scale={1}
              loading="eager"
              fetchPriority="high"
              overlay={
                <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-white/90 to-transparent" />
              }
            />
          </div>
        </StageShell>
      </motion.div>

      {/* Atlas peek card — offset below-right, clear separation */}
      <motion.div
        className="absolute -bottom-12 -right-2 z-20 hidden w-[240px] sm:block lg:-right-6"
        initial={{ opacity: 0, y: 24, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.7, delay: 0.6, ease: 'easeOut' }}
      >
        <StageShell
          accentHex={sceneManifest.governance.accentHex}
          label={t(sceneManifest.governance.windowLabelKey)}
          className="shadow-[0_24px_48px_rgba(15,23,42,0.14)]"
        >
          <div className="h-[150px]">
            <ScreenshotStageAsset
              src={atlas}
              alt={t(sceneManifest.governance.labelKey)}
              imageClassName="object-contain bg-white"
              objectPosition="center center"
              scale={0.94}
              loading="eager"
            />
          </div>
        </StageShell>
      </motion.div>

      {/* Subtle accent glow behind the main card */}
      <div
        className="absolute -inset-8 -z-10 rounded-[40px] opacity-60 blur-3xl"
        style={{
          background:
            'radial-gradient(ellipse at 60% 40%, hsl(var(--accent) / 0.16) 0%, hsl(252 70% 62% / 0.07) 50%, transparent 80%)',
        }}
      />
    </div>
  )
}
