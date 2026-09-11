// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { CSSProperties } from 'react'
import { ZoomIn } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getHomeScreenshotForTheme } from './homeScreenshotAssets'

type ScreenshotStageAssetProps = {
  src: string
  alt: string
  mobilePosition?: string
  mobileScale?: number
}

export function ScreenshotExpandLink({ src, alt }: Pick<ScreenshotStageAssetProps, 'src' | 'alt'>) {
  const { theme } = useTheme()
  const { t } = useUiLocale()
  return (
    <a href={getHomeScreenshotForTheme(src, theme)} target="_blank" rel="noopener noreferrer"
      aria-label={`${alt} · ${t('home.screenshot.expand')}`}
      className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-[hsl(var(--lp-ink)/0.6)] hover:text-[hsl(var(--lp-ink))]">
      <ZoomIn className="h-3.5 w-3.5" />{t('home.screenshot.expand')}
    </a>
  )
}

export function ScreenshotStageAsset({ src, alt, mobilePosition = 'center top', mobileScale = 1 }: ScreenshotStageAssetProps) {
  const { theme } = useTheme()
  const { t } = useUiLocale()
  const resolvedSrc = getHomeScreenshotForTheme(src, theme)
  return (
    <a className="lp-screenshot group relative block h-full w-full overflow-hidden"
      href={resolvedSrc} target="_blank" rel="noopener noreferrer" aria-label={`${alt} · ${t('home.screenshot.expand')}`}
      style={{ '--screenshot-mobile-position': mobilePosition, '--screenshot-mobile-scale': mobileScale } as CSSProperties}>
      <img src={resolvedSrc} alt={alt} className="h-full w-full object-contain" loading="lazy" decoding="async" draggable={false} />
    </a>
  )
}
