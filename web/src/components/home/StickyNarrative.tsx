// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useMemo } from 'react'
import { homeNarrativeActs } from '@/components/home/homeContent'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useNarrativeScroll } from '@/components/home/useNarrativeScroll'
import { NarrativeAct } from '@/components/home/NarrativeAct'
import { ProductStage } from '@/components/home/ProductStage'
import { sceneManifest } from '@/components/home/screenshotManifest'
import type { NarrativeActs } from '@/components/home/useNarrativeScroll'

export function StickyNarrative() {
    const { sectionRef, activeAct, prefersReducedMotion } = useNarrativeScroll()
    const { t } = useUiLocale()

    const acts = useMemo(
        () => homeNarrativeActs.map((act, i) => {
            const entry = sceneManifest[act.sceneId]
            return {
                eyebrow: t(act.eyebrowKey),
                title: t(act.titleKey),
                description: t(act.descriptionKey),
                bullets: [
                    t(act.bullets[0]),
                    t(act.bullets[1]),
                    t(act.bullets[2]),
                ],
                accentHex: entry.accentHex,
                stageLabel: t(entry.labelKey),
                actIndex: i as NarrativeActs,
                stepLabel: act.stepLabel,
                variant: act.variant,
            }
        }),
        [t],
    )

    const activeEntry = acts[activeAct]

    return (
        <section id="narrative" ref={sectionRef} className="relative bg-card px-6 pb-6 pt-14 sm:px-8 lg:px-12 lg:pb-10 lg:pt-20">
            {/* Top divider */}
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-foreground/6 to-transparent" />

            <div className="mx-auto max-w-7xl">
                <div className="mb-12 grid gap-6 pt-2 lg:grid-cols-[minmax(0,540px)_1fr] lg:items-end">
                    <div>
                        <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                            {t('home.workflow.eyebrow')}
                        </div>
                        <h2 className="mt-4 max-w-[560px] font-sans tracking-tight text-[34px] font-bold leading-[1.08] text-foreground sm:text-[42px]">
                            {t('home.workflow.title')}
                        </h2>
                    </div>
                    <div className="max-w-[520px] text-[15px] leading-8 text-muted-foreground">
                        {t('home.workflow.description')}
                    </div>
                </div>

                <div className="grid gap-14 lg:grid-cols-[minmax(0,0.84fr)_minmax(0,1.16fr)] lg:gap-16">
                    <div className="relative">
                        {acts.map((act) => (
                            <div key={act.actIndex}>
                                <NarrativeAct
                                    eyebrow={act.eyebrow}
                                    title={act.title}
                                    description={act.description}
                                    bullets={act.bullets}
                                    isActive={activeAct === act.actIndex}
                                    accentHex={act.accentHex}
                                    prefersReducedMotion={prefersReducedMotion}
                                    stepLabel={act.stepLabel}
                                    variant={act.variant}
                                />

                                {/* Mobile stage — clean accent bar, no card wrapper */}
                                <div className="mb-12 lg:hidden">
                                    <div className="flex items-center gap-3 px-1 pb-3">
                                        <div
                                            className="h-[3px] w-8 rounded-full"
                                            style={{ backgroundColor: act.accentHex }}
                                        />
                                        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground/60">
                                            {act.stageLabel}
                                        </span>
                                    </div>
                                    <div className="h-[56vh] overflow-hidden rounded-[28px] border border-foreground/6 shadow-[0_24px_48px_rgba(15,23,42,0.06)]">
                                        <ProductStage
                                            activeAct={act.actIndex}
                                            prefersReducedMotion={prefersReducedMotion}
                                        />
                                    </div>
                                </div>
                            </div>
                        ))}
                        <div className="min-h-[36vh]" aria-hidden="true" />
                    </div>

                    {/* Desktop sticky stage — no card wrapper */}
                    <div className="hidden lg:block">
                        <div className="sticky top-[8vh]">
                            {/* Step info bar */}
                            <div className="mb-4 grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-1">
                                <div>
                                    <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/60">
                                        {t('home.workflow.currentStep')}
                                    </div>
                                    <div className="mt-2 text-lg font-semibold text-foreground">
                                        {activeEntry.title}
                                    </div>
                                </div>
                                <div className="flex items-center gap-1.5 self-start font-mono text-[12px] font-bold tracking-[0.1em] text-muted-foreground/60">
                                    <span style={{ color: activeEntry.accentHex }}>{activeEntry.stepLabel}</span>
                                    <span className="text-muted-foreground/40">/</span>
                                    <span>05</span>
                                </div>
                            </div>

                            {/* Progress segments — replaces pill badges */}
                            <div className="mb-5 flex gap-1.5 px-1">
                                {acts.map((act) => {
                                    const isActive = act.actIndex === activeAct
                                    const isPast = act.actIndex < activeAct
                                    return (
                                        <div
                                            key={act.stepLabel}
                                            className="h-[3px] flex-1 rounded-full transition-all duration-500"
                                            style={{
                                                backgroundColor: isActive
                                                    ? act.accentHex
                                                    : isPast
                                                      ? `${act.accentHex}40`
                                                      : 'hsl(var(--foreground) / 0.06)',
                                            }}
                                        />
                                    )
                                })}
                            </div>

                            <div className="h-[78vh]">
                                <ProductStage
                                    activeAct={activeAct}
                                    prefersReducedMotion={prefersReducedMotion}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    )
}
