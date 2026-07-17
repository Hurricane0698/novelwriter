// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView, useReducedMotion } from 'framer-motion'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { NwButton } from '@/components/ui/nw-button'
import { StageShell } from '@/components/home/StageShell'
import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { isHostedRuntime } from '@/lib/runtimeMode'

/**
 * Closing CTA — rich composition with product preview.
 *
 * Design intent: not a bare text-and-button ending. Shows a fading
 * product screenshot above the CTA to remind users what they'll get,
 * flanked by impactful stats. Warm gradient background for energy.
 */
export function ClosingCTA() {
  const { isLoggedIn } = useAuth()
  const { t } = useUiLocale()
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.2 })
  const prefersReducedMotion = useReducedMotion()
  const startDestination = isHostedRuntime() && !isLoggedIn ? '/login' : '/library'
  const demoDestination = '/demo'
  const shouldAnimateAmbient = inView && !prefersReducedMotion

  const stats = [
    { value: t('home.cta.stat.length'), label: t('home.cta.stat.length.label') },
    { value: t('home.cta.stat.model'), label: t('home.cta.stat.model.label') },
    { value: t('home.cta.stat.context'), label: t('home.cta.stat.context.label') },
  ]

  return (
    <section ref={ref} className="relative overflow-hidden">
      {/* Warm gradient background */}
      <div
        className="absolute inset-0"
        style={{
          background: `linear-gradient(to bottom, hsl(var(--lp-cta-from)), hsl(var(--lp-cta-via)), hsl(var(--lp-cta-to)))`,
        }}
      />

      {/* Ambient orbs */}
      <motion.div
        className="absolute left-[20%] top-[20%] h-[400px] w-[400px] rounded-full opacity-[0.06]"
        style={{ background: 'radial-gradient(circle, #f59e0b 0%, transparent 70%)' }}
        animate={shouldAnimateAmbient ? { x: [0, 20, -10, 0], y: [0, -15, 10, 0] } : { x: 0, y: 0 }}
        transition={shouldAnimateAmbient ? { duration: 20, repeat: Infinity, ease: 'easeInOut' } : { duration: 0 }}
      />
      <motion.div
        className="absolute bottom-[30%] right-[15%] h-[350px] w-[350px] rounded-full opacity-[0.04]"
        style={{ background: 'radial-gradient(circle, #14b8a6 0%, transparent 70%)' }}
        animate={shouldAnimateAmbient ? { x: [0, -15, 15, 0], y: [0, 10, -20, 0] } : { x: 0, y: 0 }}
        transition={shouldAnimateAmbient ? { duration: 24, repeat: Infinity, ease: 'easeInOut' } : { duration: 0 }}
      />

      <div className="relative mx-auto max-w-7xl px-6 pb-12 pt-14 sm:px-8 lg:px-12 lg:pb-16 lg:pt-20">
        {/* Product preview — fading screenshot */}
        <motion.div
          className="mx-auto mb-12 max-w-[800px]"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        >
          <div className="relative">
            <StageShell
              accentHex={sceneManifest.continuation.accentHex}
              label={t(sceneManifest.continuation.windowLabelKey)}
              className="shadow-[0_40px_80px_rgba(15,23,42,0.08)]"
            >
              <div className="h-[200px] sm:h-[260px] lg:h-[300px]">
                <ScreenshotStageAsset
                  src={homeScreenshotAssets.studioWorkspace}
                  alt={t('home.cta.previewAlt')}
                  objectPosition="30% 0%"
                  scale={1.0}
                />
              </div>
            </StageShell>
            {/* Fade-out at bottom */}
            <div
              className="absolute inset-x-0 bottom-0 h-32"
              style={{
                background: `linear-gradient(to top, hsl(var(--lp-cta-via)), hsl(var(--lp-cta-via) / 0.8), transparent)`,
              }}
            />
          </div>
        </motion.div>

        {/* CTA text */}
        <motion.div
          className="flex flex-col items-center text-center"
          initial={{ opacity: 0, y: 24 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.15, ease: 'easeOut' }}
        >
          <h2
            className="max-w-[600px] font-mono text-[32px] font-bold leading-[1.12] text-foreground sm:text-[40px]"
          >
            {t('home.cta.title')}
          </h2>

          <p className="mt-5 max-w-[500px] text-[15px] leading-8 text-muted-foreground">
            {t('home.cta.description')}
          </p>

          {/* Stats row */}
          <div className="mt-12 flex flex-wrap justify-center gap-6 sm:gap-8">
            {stats.map((s, i) => (
              <motion.div
                key={s.label}
                className="text-center"
                initial={{ opacity: 0, y: 16 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.4, delay: 0.25 + i * 0.08 }}
              >
                <div className="flex items-baseline justify-center gap-0.5">
                  <span className="font-mono text-[36px] font-extrabold text-foreground">
                    {s.value}
                  </span>
                </div>
                <div className="mt-1 text-[12px] font-medium text-muted-foreground">
                  {s.label}
                </div>
              </motion.div>
            ))}
          </div>

          {/* CTA buttons */}
          <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
            <NwButton
              asChild
              variant="accent"
              className="rounded-full px-8 py-3.5 text-base font-medium bg-foreground border-foreground text-background shadow-[0_8px_24px_rgba(15,23,42,0.12)] hover:bg-foreground/90"
            >
              <Link
                to={startDestination}
                onClick={() => {
                  void trackHostedAnalyticsEvent('acquisition_cta_click', {
                    meta: { cta: 'footer', destination: startDestination },
                  })
                }}
              >
                {t('home.cta.button')}
              </Link>
            </NwButton>
            <NwButton
              asChild
              variant="ghost"
              className="rounded-full border border-border px-7 py-3 text-base font-medium"
            >
              <Link
                to={demoDestination}
                onClick={() => {
                  void trackHostedAnalyticsEvent('acquisition_cta_click', {
                    meta: { cta: 'footer_demo', destination: demoDestination },
                  })
                }}
              >
                {t('home.hero.cta.demo')} →
              </Link>
            </NwButton>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
