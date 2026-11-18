// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { Link } from 'react-router-dom'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { NwButton } from '@/components/ui/nw-button'
import { WorldLatticeStage } from '@/components/home/stage/WorldLatticeStage'

export function HeroSection() {
  const { t } = useUiLocale()

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
                to="/library"
                data-testid="home-start-writing"
              >
                {t('home.hero.cta')}
              </Link>
            </NwButton>
          </div>
        </div>

        <div className="mt-8 sm:mt-10">
          <WorldLatticeStage />
        </div>
      </div>
    </section>
  )
}
