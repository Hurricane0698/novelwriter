// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'

type DetailCard = {
  label: string
  description: string
  screenshot?: string
  imageMode?: 'cover' | 'contain'
  imageHeight?: number
  objectPosition?: string
  scale?: number
  accentHex: string
}

export function DetailsMatter() {
  const { t } = useUiLocale()
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.15 })
  const details: DetailCard[] = [
    {
      label: t('home.details.card1.label'),
      description: t('home.details.card1.description'),
      screenshot: homeScreenshotAssets.draftReviewHighlight,
      imageMode: 'contain',
      imageHeight: 112,
      accentHex: '#5b6bf0',
    },
    {
      label: t('home.details.card2.label'),
      description: t('home.details.card2.description'),
      screenshot: homeScreenshotAssets.atlasEntityEdit,
      objectPosition: '50% 86%',
      scale: 1.42,
      accentHex: '#4a7de8',
    },
    {
      label: t('home.details.card3.label'),
      description: t('home.details.card3.description'),
      screenshot: homeScreenshotAssets.studioWrite,
      objectPosition: '26% 2%',
      scale: 1.28,
      accentHex: '#7a5cf0',
    },
    {
      label: t('home.details.card4.label'),
      description: t('home.details.card4.description'),
      screenshot: homeScreenshotAssets.copilotChat,
      objectPosition: '50% 80%',
      scale: 1.34,
      accentHex: '#7a5cf0',
    },
  ]

  return (
    <section className="relative overflow-hidden bg-[hsl(var(--lp-surface))] py-14 lg:py-20" ref={ref}>
      {/* Top divider */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-foreground/6 to-transparent" />
      {/* Bottom gradient fade — seamless transition into CTA warm gradient */}
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-[hsl(var(--lp-cta-via))]" />

      <div className="relative mx-auto max-w-7xl px-6 sm:px-8 lg:px-12">
        {/* Section header */}
        <motion.div
          className="mb-12"
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
        >
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {t('home.details.section.eyebrow')}
          </div>
          <h2 className="mt-4 max-w-[560px] font-sans tracking-tight text-[32px] font-bold leading-[1.12] text-foreground sm:text-[40px]">
            {t('home.details.section.title')}
          </h2>
          <p className="mt-5 max-w-[520px] text-[15px] leading-8 text-muted-foreground">
            {t('home.details.section.description')}
          </p>
        </motion.div>

        {/* Detail grid — 2×2 */}
        <div className="grid gap-4 sm:grid-cols-2">
          {details.map((detail, i) => (
            <motion.div
              key={detail.label}
              className="group relative overflow-hidden rounded-2xl border border-foreground/6 bg-card/70 backdrop-blur-sm"
              initial={{ opacity: 0, y: 24 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.08 * i }}
            >
              {/* Screenshot crop (if available) */}
              {detail.screenshot && (
                <div
                  className={cn(
                    'relative overflow-hidden border-b border-foreground/4',
                    detail.imageMode === 'contain' ? 'bg-white px-4 py-4' : 'bg-white/70',
                  )}
                  style={{ height: detail.imageHeight ?? 140 }}
                >
                  <img
                    src={detail.screenshot}
                    alt=""
                    className={cn(
                      'w-full transition-opacity duration-500 group-hover:opacity-95',
                      detail.imageMode === 'contain'
                        ? 'h-full object-contain opacity-100'
                        : 'h-full object-cover opacity-70 group-hover:opacity-90',
                    )}
                    style={{
                      objectPosition: detail.objectPosition,
                      transform: detail.imageMode === 'contain' ? undefined : `scale(${detail.scale ?? 1})`,
                      transformOrigin: detail.objectPosition,
                    }}
                    loading="lazy"
                    draggable={false}
                  />
                  {detail.imageMode !== 'contain' && (
                    <div className="absolute inset-x-0 top-0 h-full bg-gradient-to-b from-transparent via-transparent to-card/80" />
                  )}
                </div>
              )}

              {/* Text content */}
              <div className="relative p-5">
                <div className="flex items-center gap-2.5">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: detail.accentHex }}
                  />
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground">
                    {detail.label}
                  </span>
                </div>
                <p className="mt-3 text-[13px] leading-7 text-muted-foreground">
                  {detail.description}
                </p>
              </div>

              {/* Hover glow */}
              <div
                className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                style={{
                  background: `radial-gradient(ellipse at 50% 50%, ${detail.accentHex}06 0%, transparent 70%)`,
                }}
              />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
