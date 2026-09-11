// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { X } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { usePerformanceMode } from '@/contexts/PerformanceModeContext'
import { journeyWorldDemo } from '@/components/home/demo/journeyWorldDemo'
import { WARP_LATTICE_FRAG } from '@/components/home/shader/warpLattice.frag'
import { readLandingPalette } from '@/components/home/shader/readLandingPalette'
import { useShaderSurface } from '@/components/home/shader/useShaderSurface'
import { LatticeFallback } from '@/components/home/stage/LatticeFallback'

const { entities, relations } = journeyWorldDemo
const knots = entities.flatMap((entity) => [entity.x, 1 - entity.y, 0])
const primaryNodes = ['tang-seng', 'sun-wukong', 'huaguo-shan', 'jingu-zhou']

export function WorldLatticeStage() {
  const { t } = useUiLocale()
  const { isLite } = usePerformanceMode()
  const reducedMotion = useReducedMotion()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [settled, setSettled] = useState(false)
  const startTime = useRef(0)
  const still = isLite || reducedMotion || settled

  useEffect(() => {
    startTime.current = performance.now()
    const timeout = window.setTimeout(() => setSettled(true), 1200)
    return () => window.clearTimeout(timeout)
  }, [])

  const state = useShaderSurface(canvasRef, {
    fragment: WARP_LATTICE_FRAG,
    animate: !still,
    maxDpr: 1.5,
    uniforms: () => {
      const palette = readLandingPalette()
      const progress = still ? 1 : Math.min(1, (performance.now() - startTime.current) / 1200)
      return {
        uResolution: [canvasRef.current?.width || 1, canvasRef.current?.height || 1],
        uOrder: 1 - Math.pow(1 - progress, 3),
        uPaper: palette.paper,
        uThread: palette.thread,
        uThreadSoft: palette.threadSoft,
        uKnots: knots,
      }
    },
  })
  const active = entities.find((entity) => entity.id === activeId)

  return (
    <div className="lp-frame lp-lattice" data-shader-state={state} onKeyDown={(event) => {
      if (event.key === 'Escape') setActiveId(null)
    }}>
      <canvas ref={canvasRef} aria-hidden="true" className={`absolute inset-0 h-full w-full ${state === 'webgl' ? 'opacity-100' : 'opacity-0'}`} />
      <LatticeFallback />
      <svg className="lp-relations" viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
        {relations.map((relation) => {
          const from = entities.find((entity) => entity.id === relation.from)!
          const to = entities.find((entity) => entity.id === relation.to)!
          const highlighted = activeId === relation.from || activeId === relation.to
          return <path key={relation.id} data-active={highlighted} d={`M ${from.x * 1000} ${from.y * 500} Q ${(from.x + to.x) * 500} ${(from.y + to.y) * 250 + 35} ${to.x * 1000} ${to.y * 500}`} vectorEffect="non-scaling-stroke" />
        })}
      </svg>
      <span className="lp-relation-label" aria-hidden="true">{t('home.lattice.relationship')}</span>
      {entities.map((entity) => (
        <button
          key={entity.id}
          type="button"
          className="lp-lattice-node"
          data-primary={primaryNodes.includes(entity.id)}
          data-entity={entity.id}
          style={{ left: `${entity.x * 100}%`, top: `${entity.y * 100}%` }}
          onPointerEnter={(event) => { if (event.pointerType !== 'touch') setActiveId(entity.id) }}
          onFocus={() => setActiveId(entity.id)}
          onClick={() => setActiveId(entity.id)}
          aria-pressed={activeId === entity.id}
        >
          <span className="lp-knot" aria-hidden="true" />
          <span className="lp-node-name">{entity.name}</span>
        </button>
      ))}
      {active && (
        <aside className="lp-lattice-detail" aria-live="polite">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-baseline gap-3">
              <strong className="text-base font-medium">{active.name}</strong>
              <span className="lp-meta">{t(`home.lattice.type.${active.type}`)}</span>
            </div>
            <button type="button" className="lp-detail-close" aria-label={t('home.lattice.close')} onClick={() => setActiveId(null)}><X size={16} /></button>
          </div>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-xs leading-relaxed">
            <dt className="text-[hsl(var(--lp-ink)/0.6)]">{t('home.lattice.label.surface')}</dt>
            <dd>{active.surface}</dd>
            <dt className="text-[hsl(var(--lp-truth))]">{t('home.lattice.label.truth')}</dt>
            <dd>{active.truth}</dd>
          </dl>
        </aside>
      )}
      <div className="lp-lattice-caption">
        <span>{t('home.lattice.source')}</span>
        <span>{entities.length} {t('home.lattice.stat.entities')} · {relations.length} {t('home.lattice.stat.relations')} · 1 {t('home.lattice.stat.systems')}</span>
      </div>
    </div>
  )
}
