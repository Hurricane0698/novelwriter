// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { Link } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { NwButton } from '@/components/ui/nw-button'
import { WorldLatticeStage } from '@/components/home/stage/WorldLatticeStage'
import { isHostedRuntime } from '@/lib/runtimeMode'

export function HeroSection() {
  const { isLoggedIn } = useAuth()
  const { t } = useUiLocale()
  const isHosted = isHostedRuntime()
  const startDestination = isHosted && !isLoggedIn ? '/login' : '/library'

  return (
    <section className="relative isolate overflow-hidden bg-[hsl(var(--lp-paper))] px-6 pb-8 pt-12 sm:px-8 sm:pt-16 lg:px-12 lg:pb-12 lg:pt-20">
      <div className="mx-auto w-full max-w-7xl">
        <div className="max-w-[1120px]">
          <h1 className="lp-display lp-hero-title">
            {t('home.hero.title')}
          </h1>
          <p className="lp-body mt-5 max-w-[660px] text-balance">{t('home.hero.description')}</p>
          <div className="lp-hero-actions mt-7 flex flex-wrap items-center gap-3">
            <NwButton
              asChild
              variant="accent"
              className="lp-cta-primary h-11 px-7 text-[15px] font-medium shadow-none"
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
                {t('home.hero.cta')}
              </Link>
            </NwButton>
            {isHosted ? (
              <NwButton
                asChild
                variant="glass"
                className="lp-cta-secondary h-11 px-6 text-[15px] font-medium shadow-none"
              >
                <a
                  href="https://github.com/Hurricane0698/novelwriter/releases/latest"
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => {
                    void trackHostedAnalyticsEvent('acquisition_cta_click', {
                      meta: { cta: 'hero_download', destination: 'github_releases' },
                    })
                  }}
                >
                  {t('home.hero.download')}
                </a>
              </NwButton>
            ) : null}
          </div>
        </div>

        <div className="mt-8 sm:mt-10">
          <WorldLatticeStage />
        </div>
      </div>
    </section>
  )
}
