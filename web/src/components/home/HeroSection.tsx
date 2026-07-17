// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { NwButton } from '@/components/ui/nw-button'
import { homeHeroStats } from '@/components/home/homeContent'
import { HeroGraphBg } from '@/components/home/HeroGraphBg'
import { HeroVisual } from '@/components/home/HeroVisual'
import { isHostedRuntime } from '@/lib/runtimeMode'

const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12 } },
}
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: 'easeOut' as const } },
}

export function HeroSection() {
  const { isLoggedIn } = useAuth()
  const { t } = useUiLocale()
  const startDestination = isHostedRuntime() && !isLoggedIn ? '/login' : '/library'
  const demoDestination = '/demo'

  return (
    <section className="relative min-h-[100svh] overflow-hidden px-6 pb-12 pt-24 sm:px-8 lg:pb-16 lg:pt-28">
      <HeroGraphBg />

      <div className="mx-auto grid w-full max-w-7xl items-center gap-12 lg:grid-cols-[minmax(0,560px)_minmax(0,1fr)] lg:gap-16">
        <motion.div
          className="relative z-10 flex flex-col items-center text-center lg:items-start lg:text-left"
          initial="hidden"
          animate="visible"
          variants={staggerContainer}
        >
          <motion.span
            variants={fadeUp}
            className="text-[11px] tracking-[0.25em] uppercase font-mono text-muted-foreground"
          >
            {t('home.hero.eyebrow')}
          </motion.span>

          <motion.h1
            variants={fadeUp}
            className="mt-6 max-w-[720px] font-mono text-[44px] font-bold leading-[1.06] text-foreground sm:text-[56px] lg:text-[64px]"
          >
            {t('home.hero.title')}
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mt-6 max-w-[560px] font-sans text-lg leading-[1.65] text-muted-foreground"
          >
            {t('home.hero.description')}
          </motion.p>

          <motion.div
            variants={fadeUp}
            className="mt-10 flex flex-wrap items-center justify-center gap-4 lg:justify-start"
          >
            <NwButton
              asChild
              variant="accent"
              className="rounded-full px-7 py-3 text-base font-medium bg-foreground border-foreground text-background hover:bg-foreground/90"
            >
              <Link
                to={demoDestination}
                data-testid="home-demo"
                onClick={() => {
                  void trackHostedAnalyticsEvent('acquisition_cta_click', {
                    meta: { cta: 'hero_demo', destination: demoDestination },
                  })
                }}
              >
                {t('home.hero.cta.demo')}
              </Link>
            </NwButton>

            <NwButton
              asChild
              variant="ghost"
              className="rounded-full border border-border px-7 py-3 text-base font-medium"
            >
              <Link
                to={startDestination}
                data-testid="home-start-writing"
                onClick={() => {
                  void trackHostedAnalyticsEvent('acquisition_cta_click', {
                    meta: { cta: 'hero_start', destination: startDestination },
                  })
                }}
              >
                {t('home.hero.cta')} →
              </Link>
            </NwButton>
          </motion.div>

          <motion.div variants={fadeUp} className="mt-8 flex w-full max-w-[560px] items-center gap-6">
            {homeHeroStats.map((item) => (
              <div key={item.labelKey} className="flex items-baseline gap-1">
                <span className="font-mono text-[28px] font-extrabold" style={{ color: item.color }}>
                  {item.value}
                </span>
                <span className="text-[13px] text-muted-foreground/70">{t(item.unitKey)}</span>
                <span className="ml-1 text-[12px] text-muted-foreground/50">{t(item.labelKey)}</span>
              </div>
            ))}
          </motion.div>
        </motion.div>

        <motion.div
          className="relative z-10 lg:pt-4"
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, delay: 0.25, ease: 'easeOut' }}
        >
          <HeroVisual />
        </motion.div>
      </div>
    </section>
  )
}
