// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { journeyWorldDemo } from '@/components/home/demo/journeyWorldDemo'

// The same fine threads remain visible with WebGL, reduced motion, and lite mode.
const threads = journeyWorldDemo.entities.flatMap((entity, index) =>
  Array.from({ length: 7 }, (_, ray) => {
    const angle = (ray / 7) * Math.PI * 2 + index * 0.63
    const x = entity.x * 1000
    const y = entity.y * 500
    const endX = x + Math.cos(angle) * 620
    const endY = y + Math.sin(angle) * 460
    return `M ${x} ${y} Q ${(x + endX) / 2 + Math.sin(angle) * 135} ${(y + endY) / 2 - Math.cos(angle) * 100} ${endX} ${endY}`
  }),
)
const stars = Array.from({ length: 82 }, (_, index) => ({
  x: ((index * 137.508) % 1000),
  y: ((index * 83.17 + 27) % 500),
}))

export function LatticeFallback() {
  return (
    <svg aria-hidden="true" className="lp-lattice-threads" viewBox="0 0 1000 500" preserveAspectRatio="none">
      {threads.map((path, index) => <path key={index} d={path} strokeDasharray={index % 3 === 0 ? '2 5' : undefined} vectorEffect="non-scaling-stroke" />)}
      {stars.map((star, index) => <circle key={index} cx={star.x} cy={star.y} r={index % 5 === 0 ? 1.9 : 1} />)}
    </svg>
  )
}
