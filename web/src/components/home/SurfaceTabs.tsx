// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef, useState } from 'react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { homeFeatureRows } from '@/components/home/homeContent'
import { ScreenshotStageAsset, ScreenshotExpandLink } from '@/components/home/ScreenshotStageAsset'
import { StageShell } from '@/components/home/StageShell'

export function SurfaceTabs() {
  const { t } = useUiLocale()
  const [active, setActive] = useState(0)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const row = homeFeatureRows[active]

  return (
    <section className="lp-section" aria-labelledby="surfaces-title">
      <div className="mx-auto max-w-7xl">
        <h2 id="surfaces-title" className="lp-h2">{t('home.surfaces.title')}</h2>
        <p className="lp-body mt-4 max-w-[640px]">{t('home.surfaces.description')}</p>
        <div className="lp-surface-tabs mt-8" role="tablist" aria-label={t('home.surfaces.title')}>
          {homeFeatureRows.map((item, index) => (
            <button key={item.id} id={`surface-tab-${item.id}`} type="button" role="tab"
              ref={(node) => { tabs.current[index] = node }}
              aria-selected={active === index} aria-controls={`surface-panel-${item.id}`} tabIndex={active === index ? 0 : -1}
              onClick={() => setActive(index)} onKeyDown={(event) => {
                let next = index
                if (event.key === 'ArrowRight') next = (index + 1) % homeFeatureRows.length
                else if (event.key === 'ArrowLeft') next = (index + homeFeatureRows.length - 1) % homeFeatureRows.length
                else if (event.key === 'Home') next = 0
                else if (event.key === 'End') next = homeFeatureRows.length - 1
                else return
                event.preventDefault()
                setActive(next)
                tabs.current[next]?.focus()
              }}>
              {t(item.eyebrowKey)}
            </button>
          ))}
        </div>
        <div id={`surface-panel-${row.id}`} role="tabpanel" aria-labelledby={`surface-tab-${row.id}`} tabIndex={0} className="mt-6">
          <StageShell label={t(row.windowLabelKey)} headerAction={<ScreenshotExpandLink src={row.screenshot} alt={t(row.altKey)} />}>
            <div className="h-[420px] sm:aspect-[4/3] sm:h-auto lg:aspect-[1336/772] lg:max-h-[720px]">
              <ScreenshotStageAsset key={row.id} src={row.screenshot} alt={t(row.altKey)}
                mobilePosition={row.id === 'copilot' ? 'right bottom' : 'center center'}
                mobileScale={row.id === 'copilot' ? 1.6 : 1} />
            </div>
          </StageShell>
          <div className="mt-5 grid gap-2 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] sm:gap-8">
            <h3 className="text-lg font-medium">{t(row.titleKey)}</h3>
            <p className="text-sm leading-7 text-[hsl(var(--lp-ink)/0.65)]">{t(row.descriptionKey)}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
