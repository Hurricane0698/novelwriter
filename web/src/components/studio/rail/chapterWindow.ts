export const ROW_HEIGHT = 38
export const ROW_STRIDE = ROW_HEIGHT + 4
export const DEFAULT_VIEWPORT_HEIGHT = 420
const OVERSCAN = 5

export function chapterWindow(count: number, top: number, height: number) {
  return {
    start: Math.max(0, Math.min(count, Math.floor(top / ROW_STRIDE) - OVERSCAN)),
    end: Math.min(count, Math.ceil((top + height) / ROW_STRIDE) + OVERSCAN),
  }
}

export function shouldRevealChapter(previous: { selection: number | null } | null, selection: number | null) {
  return previous === null || previous.selection !== selection
}

export function restoreChapterAnchor(
  previous: { chapterNumber: number }[],
  indices: Map<number, number>,
  anchor: { index: number; offset: number },
) {
  // If the anchor itself was deleted/filtered, retain its closest surviving
  // neighbour (prefer the following row). Chapter numbers are stable identities.
  for (let distance = 0; distance < previous.length; distance += 1) {
    for (const index of [anchor.index + distance, anchor.index - distance]) {
      const next = indices.get(previous[index]?.chapterNumber)
      if (next !== undefined) return next * ROW_STRIDE + anchor.offset
    }
  }
  return 0
}
