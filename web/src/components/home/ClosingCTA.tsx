// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { Link } from 'react-router-dom'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { NwButton } from '@/components/ui/nw-button'

export function ClosingCTA() {
  const { t } = useUiLocale()

  return (
    <section className="lp-section">
      <div className="mx-auto max-w-7xl">
        <div className="max-w-[640px]">
          <h2 className="lp-h2">{t('home.cta.title')}</h2>
          <p className="lp-body mt-4 max-w-[520px]">{t('home.cta.description')}</p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <NwButton
              asChild
              variant="accent"
              className="lp-cta-primary h-11 px-7 text-[15px] font-medium shadow-none"
            >
              <Link
                to="/library"
              >
                {t('home.cta.button')}
              </Link>
            </NwButton>
          </div>

          <p className="lp-meta mt-8 max-w-[560px] leading-relaxed">{t('home.cta.facts')}</p>
        </div>
      </div>
    </section>
  )
}
