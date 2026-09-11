// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef, useState } from 'react'
import { useScroll, useMotionValueEvent, useReducedMotion } from 'framer-motion'
import { HOME_NARRATIVE_ACT_COUNT } from '@/components/home/homeContent'

export type NarrativeActs = 0 | 1 | 2 | 3 | 4

export function useNarrativeScroll() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const [activeAct, setActiveAct] = useState<NarrativeActs>(0)
  const prefersReducedMotion = useReducedMotion()
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start 80px', 'end end'] })

  useMotionValueEvent(scrollYProgress, 'change', (progress) => {
    setActiveAct(Math.min(HOME_NARRATIVE_ACT_COUNT - 1, Math.max(0,
      Math.floor(progress * HOME_NARRATIVE_ACT_COUNT))) as NarrativeActs)
  })

  const scrollToAct = (index: NarrativeActs) => {
    const track = sectionRef.current
    if (!track) return
    const start = track.getBoundingClientRect().top + window.scrollY - 80
    const distance = track.offsetHeight - window.innerHeight + 80
    // Move into the chosen step's interval; the card itself supplies the motion.
    window.scrollTo({ top: start + distance * (index + 0.5) / HOME_NARRATIVE_ACT_COUNT, behavior: 'instant' })
    setActiveAct(index)
  }

  return { sectionRef, activeAct, scrollToAct, prefersReducedMotion: prefersReducedMotion ?? false }
}
