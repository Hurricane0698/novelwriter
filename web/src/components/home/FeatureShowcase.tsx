// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { StageShell } from '@/components/home/StageShell'
import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { homeFeatureRows } from '@/components/home/homeContent'
import { useUiLocale } from '@/contexts/UiLocaleContext'

/**
 * Feature overview — three product surfaces at a glance.
 *
 * Role: macro orientation. Tell the visitor "what is this product made of"
 * before the workflow section explains "how do I use it step by step".
 * Keep copy benefit-oriented and short; avoid repeating workflow details.
 */

type FeatureRow = {
  id: string
  eyebrow: string
  title: string
  description: string
  screenshot: string
  alt: string
  accentHex: string
  label: string
  objectPosition: string
  scale: number
  imageClassName?: string
  imageRight: boolean
}

export function FeatureShowcase() {
  const { t } = useUiLocale()
  const features: FeatureRow[] = homeFeatureRows.map((feature) => ({
    id: feature.id,
    eyebrow: t(feature.eyebrowKey),
    title: t(feature.titleKey),
    description: t(feature.descriptionKey),
    screenshot: feature.screenshot,
    alt: t(feature.altKey),
    accentHex: feature.accentHex,
    label: t(feature.windowLabelKey),
    objectPosition: feature.objectPosition,
    scale: feature.scale,
    imageClassName: feature.imageClassName,
    imageRight: feature.imageRight,
  }))

  return (
    <section className="relative overflow-hidden bg-[hsl(var(--lp-surface))] py-14 lg:py-20">
      {/* Section divider — top edge */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-foreground/6 to-transparent" />

      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-12">
        {/* Section header */}
        <div className="mb-14 max-w-[640px]">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            {t('home.feature.section.eyebrow')}
          </div>
          <h2 className="mt-4 font-sans tracking-tight text-[32px] font-bold leading-[1.12] text-foreground sm:text-[40px]">
            {t('home.feature.section.title')}
          </h2>
          <p className="mt-5 text-[15px] leading-8 text-muted-foreground">
            {t('home.feature.section.description')}
          </p>
        </div>

        {/* Feature rows */}
        <div className="flex flex-col gap-20 lg:gap-24">
          {features.map((feature) => (
            <FeatureRowComponent key={feature.id} feature={feature} />
          ))}
        </div>
      </div>

      {/* Section divider — bottom edge */}
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-foreground/6 to-transparent" />
    </section>
  )
}

function FeatureRowComponent({ feature }: { feature: FeatureRow }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.2 })

  const textContent = (
    <div className="flex flex-col justify-center lg:py-8">
      <span
        className="inline-flex w-fit rounded-full border px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.18em]"
        style={{
          color: feature.accentHex,
          borderColor: `${feature.accentHex}33`,
          backgroundColor: `${feature.accentHex}10`,
        }}
      >
        {feature.eyebrow}
      </span>
      <h3 className="mt-5 font-sans tracking-tight text-[26px] font-bold leading-[1.16] text-foreground sm:text-[30px]">
        {feature.title}
      </h3>
      <p className="mt-4 max-w-[440px] text-[15px] leading-8 text-muted-foreground">
        {feature.description}
      </p>
    </div>
  )

  const imageContent = (
    <div className="relative">
      <StageShell
        accentHex={feature.accentHex}
        label={feature.label}
        className="shadow-[0_30px_60px_rgba(15,23,42,0.10)]"
      >
        <div className="h-[300px] sm:h-[380px] lg:h-[440px]">
          <ScreenshotStageAsset
            src={feature.screenshot}
            alt={feature.alt}
            imageClassName={feature.imageClassName}
            objectPosition={feature.objectPosition}
            scale={feature.scale}
            overlay={
              <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-white/80 to-transparent" />
            }
          />
        </div>
      </StageShell>
      {/* Ambient glow behind screenshot */}
      <div
        className="absolute -inset-6 -z-10 rounded-[40px] opacity-40 blur-3xl"
        style={{
          background: `radial-gradient(ellipse at center, ${feature.accentHex}12 0%, transparent 70%)`,
        }}
      />
    </div>
  )

  return (
    <motion.div
      ref={ref}
      className={`grid items-center gap-10 lg:gap-16 ${
        feature.imageRight
          ? 'lg:grid-cols-[minmax(0,0.45fr)_minmax(0,0.55fr)]'
          : 'lg:grid-cols-[minmax(0,0.55fr)_minmax(0,0.45fr)]'
      }`}
      initial={{ opacity: 0, y: 40 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, ease: 'easeOut' }}
    >
      {/* On mobile: always image first, then text */}
      {feature.imageRight ? (
        <>
          <div className="order-2 lg:order-1">{textContent}</div>
          <div className="order-1 lg:order-2">{imageContent}</div>
        </>
      ) : (
        <>
          {imageContent}
          {textContent}
        </>
      )}
    </motion.div>
  )
}
