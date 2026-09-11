// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState } from 'react'
import { LockKeyhole } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { chapter27Excerpt } from '@/components/home/demo/chapter27Excerpt'
import { journeyWorldDemo } from '@/components/home/demo/journeyWorldDemo'
import { LatticeFallback } from '@/components/home/stage/LatticeFallback'

const entities = journeyWorldDemo.entities.filter((entity) =>
  (chapter27Excerpt.injection.entityIds as readonly string[]).includes(entity.id),
)

export function InjectionSection() {
  const { t } = useUiLocale()
  const [layer, setLayer] = useState<'surface' | 'truth'>('surface')
  const [activeId, setActiveId] = useState('baigu-furen')
  const active = journeyWorldDemo.entities.find((entity) => entity.id === activeId)!

  return (
    <section className="lp-section" aria-labelledby="injection-title">
      <div className="mx-auto max-w-7xl">
        <h2 id="injection-title" className="lp-h2">{t('home.injection.title')}</h2>
        <p className="lp-body mt-4 max-w-[640px]">{t('home.injection.description')}</p>
        <div className="lp-frame lp-injection-stage mt-9">
          <LatticeFallback />
          <div className="relative grid items-start gap-8 p-6 sm:p-9 lg:grid-cols-[minmax(0,1.6fr)_minmax(260px,1fr)] lg:gap-14 lg:p-12">
            <article>
              <p className="lp-meta mb-5">{t('home.injection.source')}</p>
              <p className="lp-excerpt">
                {chapter27Excerpt.spans.map((span, index) => {
                  if (span.kind === 'text') return <span key={index}>{span.text}</span>
                  const id = span.kind === 'entity' ? span.entityId : span.systemId
                  return (
                    <button key={index} type="button" className="lp-node-highlight" data-active={activeId === id}
                      onPointerEnter={(event) => { if (event.pointerType !== 'touch') setActiveId(id) }}
                      onFocus={() => setActiveId(id)} onClick={() => setActiveId(id)} aria-pressed={activeId === id}>
                      {span.text}
                    </button>
                  )
                })}
              </p>
            </article>
            <aside className="lp-setting-card">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-xl font-medium">{active.name}</h3>
                <span className="lp-meta">{t(`home.lattice.type.${active.type}`)}</span>
              </div>
              <div className="lp-layer-switch mt-5" aria-label={t('home.injection.layers')}>
                {(['surface', 'truth'] as const).map((value) => (
                  <button key={value} type="button" aria-pressed={layer === value} onClick={() => setLayer(value)}>
                    {t(`home.injection.layer.${value}`)}
                    {value === 'truth' && <LockKeyhole size={13} aria-hidden="true" />}
                  </button>
                ))}
              </div>
              <div className="min-h-[140px] pt-5" aria-live="polite">
                <p className="text-[15px] leading-7">{active[layer]}</p>
                <p className="mt-4 text-xs leading-6 text-[hsl(var(--lp-ink)/0.6)]">
                  {t(layer === 'truth' ? 'home.injection.truthNote' : 'home.injection.surfaceNote')}
                </p>
              </div>
            </aside>
          </div>
          <div className="lp-injection-links" aria-label={t('home.injection.relations')}>
            {entities.map((entity) => (
              <button key={entity.id} type="button" aria-pressed={entity.id === activeId} onClick={() => setActiveId(entity.id)}>
                <span aria-hidden="true" />{entity.name}
              </button>
            ))}
          </div>
        </div>
        <p className="lp-meta mt-4">{t('home.injection.footnote', {
          entities: entities.length,
          relations: chapter27Excerpt.injection.relationIds.length,
          systems: chapter27Excerpt.injection.systemIds.length,
        })}</p>
      </div>
    </section>
  )
}
