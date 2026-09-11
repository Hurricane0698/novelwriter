// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { AnimatePresence, motion } from 'framer-motion'
import { homeNarrativeActs, HOME_NARRATIVE_ACT_COUNT } from '@/components/home/homeContent'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useNarrativeScroll } from '@/components/home/useNarrativeScroll'
import { NarrativeAct } from '@/components/home/NarrativeAct'
import { ProductStage } from '@/components/home/ProductStage'
import type { NarrativeActs } from '@/components/home/useNarrativeScroll'

export function StickyNarrative() {
  const { sectionRef, activeAct, scrollToAct, prefersReducedMotion } = useNarrativeScroll()
  const { t } = useUiLocale()
  const current = homeNarrativeActs[activeAct]

  return (
    <section id="narrative" className="lp-section" aria-labelledby="workflow-title">
      <div className="mx-auto max-w-7xl">
        <div className="mb-10 grid gap-4 lg:grid-cols-2 lg:items-end">
          <h2 id="workflow-title" className="lp-h2">{t('home.workflow.title')}</h2>
          <p className="lp-body">{t('home.workflow.description')}</p>
        </div>
        <div ref={sectionRef} className="lp-workflow-track">
          <div className="lp-workflow-sticky">
            <div className="lp-workflow-copy">
              <nav className="lp-workflow-nav" aria-label={t('home.workflow.currentStep')}>
                {homeNarrativeActs.map((act, index) => (
                  <button key={act.sceneId} type="button"
                    aria-current={index === activeAct ? 'step' : undefined}
                    onClick={() => scrollToAct(index as NarrativeActs)}
                    onKeyDown={(event) => {
                      let next = index
                      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % HOME_NARRATIVE_ACT_COUNT
                      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + HOME_NARRATIVE_ACT_COUNT - 1) % HOME_NARRATIVE_ACT_COUNT
                      else if (event.key === 'Home') next = 0
                      else if (event.key === 'End') next = HOME_NARRATIVE_ACT_COUNT - 1
                      else return
                      event.preventDefault()
                      event.currentTarget.parentElement?.querySelectorAll('button')[next]?.focus({ preventScroll: true })
                      scrollToAct(next as NarrativeActs)
                    }}>
                    <span className="font-mono text-xs">{act.stepLabel}</span>
                    <span>{t(act.eyebrowKey)}</span>
                  </button>
                ))}
              </nav>
              <div className="lp-workflow-description">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={activeAct}
                    initial={prefersReducedMotion ? false : { opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: prefersReducedMotion ? 0 : -12 }}
                    transition={{ duration: prefersReducedMotion ? 0 : 0.2 }}>
                    <NarrativeAct title={t(current.titleKey)} description={t(current.descriptionKey)} />
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
            <div className="lp-workflow-stage" data-testid="home-workflow-stage" data-act={current.sceneId}>
              <ProductStage activeAct={activeAct} prefersReducedMotion={prefersReducedMotion} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
