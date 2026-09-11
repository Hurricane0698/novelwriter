// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { Link } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { NwButton } from '@/components/ui/nw-button'
import { isHostedRuntime } from '@/lib/runtimeMode'

const RELEASES_LATEST = 'https://github.com/Hurricane0698/novelwriter/releases/latest'

export function DownloadRow() {
  const { t } = useUiLocale()
  if (!isHostedRuntime()) return null

  return (
    <div className="flex flex-wrap items-center gap-3">
      <a
        href={RELEASES_LATEST}
        className="lp-cta-secondary inline-flex h-10 items-center rounded-full px-5 text-sm font-medium"
        onClick={() => {
          void trackHostedAnalyticsEvent('acquisition_cta_click', {
            meta: { cta: 'download_windows', destination: 'github_releases' },
          })
        }}
      >
        {t('home.download.windows')}
      </a>
      <a
        href={RELEASES_LATEST}
        className="lp-cta-secondary inline-flex h-10 items-center rounded-full px-5 text-sm font-medium"
        onClick={() => {
          void trackHostedAnalyticsEvent('acquisition_cta_click', {
            meta: { cta: 'download_macos', destination: 'github_releases' },
          })
        }}
      >
        {t('home.download.macos')}
      </a>
    </div>
  )
}

export function ClosingCTA() {
  const { isLoggedIn } = useAuth()
  const { t } = useUiLocale()
  const startDestination = isHostedRuntime() && !isLoggedIn ? '/login' : '/library'

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
            <DownloadRow />
          </div>

          <p className="lp-meta mt-8 max-w-[560px] leading-relaxed">{t('home.cta.facts')}</p>
        </div>
      </div>
    </section>
  )
}
