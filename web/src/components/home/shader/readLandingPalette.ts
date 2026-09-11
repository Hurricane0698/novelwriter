// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

export type LandingPalette = {
  paper: [number, number, number]
  ink: [number, number, number]
  frame: [number, number, number]
  thread: [number, number, number]
  threadSoft: [number, number, number]
  knot: [number, number, number]
  truth: [number, number, number]
}

function parseHslChannels(value: string | undefined): [number, number, number] | null {
  if (!value) return null
  const parts = value.trim().split(/\s+/).map(parseFloat)
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return null
  const [h, s, l] = parts
  return hslToRgb(h / 360, s / 100, l / 100)
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) {
    const v = l
    return [v, v, v]
  }
  const hue2rgb = (p: number, q: number, t: number) => {
    let tt = t
    if (tt < 0) tt += 1
    if (tt > 1) tt -= 1
    if (tt < 1 / 6) return p + (q - p) * 6 * tt
    if (tt < 1 / 2) return q
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6
    return p
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [hue2rgb(p, q, h + 1 / 3), hue2rgb(p, q, h), hue2rgb(p, q, h - 1 / 3)]
}

export function readLandingPalette(): LandingPalette {
  if (typeof window === 'undefined') {
    return {
      paper: [1, 1, 1],
      ink: [0, 0, 0],
      frame: [0.97, 0.97, 0.97],
      thread: [0.357, 0.42, 0.941],
      threadSoft: [0.76, 0.827, 1],
      knot: [0.122, 0.169, 0.522],
      truth: [1, 0.72, 0.1],
    }
  }

  const styles = getComputedStyle(document.documentElement)
  const read = (name: string) => parseHslChannels(styles.getPropertyValue(name).trim())

  return {
    paper: read('--lp-paper') ?? [1, 1, 1],
    ink: read('--lp-ink') ?? [0, 0, 0],
    frame: read('--lp-frame') ?? [0.97, 0.97, 0.97],
    thread: read('--lp-thread') ?? [0.357, 0.42, 0.941],
    threadSoft: read('--lp-thread-soft') ?? [0.76, 0.827, 1],
    knot: read('--lp-knot') ?? [0.122, 0.169, 0.522],
    truth: read('--lp-truth') ?? [1, 0.72, 0.1],
  }
}
