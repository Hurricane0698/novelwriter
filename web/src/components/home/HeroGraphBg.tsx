// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { motion, useReducedMotion } from 'framer-motion'

/**
 * Hero background — celestial wash.
 *
 * Light mode: a periwinkle sky that saturates at the top of the viewport and
 * dissolves into cloud white toward the fold (reference: soft sky gradient).
 * Dark mode: a deep-space nebula in the same periwinkle family; the global
 * starfield layer (AnimatedBackground) provides the star speckle behind it.
 */
export function HeroGraphBg() {
  const reduce = useReducedMotion()

  return (
    <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none" aria-hidden="true">
      {/* Sky wash: saturated at top, dissolving toward the fold. Token-driven so it adapts per theme. */}
      <div
        className="absolute inset-x-0 top-0 h-[85%]"
        style={{
          background:
            'linear-gradient(180deg, hsl(var(--accent) / 0.34) 0%, hsl(var(--accent) / 0.16) 38%, hsl(var(--background) / 0) 80%)',
        }}
      />

      {/* Cloud bloom — soft white radial rising from the lower third (light); reads as nebula glow in dark. */}
      <motion.div
        className="absolute left-[8%] top-[38%] h-[520px] w-[720px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(ellipse, hsl(var(--background) / 0.9) 0%, transparent 70%)' }}
        animate={reduce ? undefined : { x: [0, 26, -12, 0], y: [0, -14, 10, 0] }}
        transition={{ duration: 26, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Periwinkle drift — upper right */}
      <motion.div
        className="absolute -right-[6%] -top-[12%] h-[560px] w-[560px] rounded-full opacity-[0.16] blur-2xl"
        style={{ background: 'radial-gradient(circle, hsl(var(--accent)) 0%, transparent 68%)' }}
        animate={reduce ? undefined : { x: [0, -22, 12, 0], y: [0, 16, -18, 0] }}
        transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Deep indigo whisper — bottom center, ties hero into the next section */}
      <motion.div
        className="absolute bottom-[2%] left-[32%] h-[380px] w-[520px] rounded-full opacity-[0.08] blur-2xl"
        style={{ background: 'radial-gradient(circle, hsl(252 70% 62%) 0%, transparent 70%)' }}
        animate={reduce ? undefined : { x: [0, 14, -16, 0], y: [0, -10, 18, 0] }}
        transition={{ duration: 30, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Fine dot grid for texture */}
      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: 'radial-gradient(circle, hsl(var(--foreground)) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }}
      />
    </div>
  )
}
