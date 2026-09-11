import { describe, expect, it } from 'vitest'
import { getStudioWorkspaceLayout, resolveStudioRightPanel } from '@/components/studio/studioWorkspaceLayout'

describe('workspace panels', () => {
  it.each([
    [false, false, false, 'hidden'], [false, false, true, 'assist'],
    [false, true, false, 'injection-summary'], [false, true, true, 'injection-summary'],
    [true, false, false, 'copilot'], [true, false, true, 'copilot'],
    [true, true, false, 'copilot'], [true, true, true, 'copilot'],
  ] as const)('resolves copilot %s, summary %s, assist %s to %s', (copilot, summary, assist, expected) => {
    expect(resolveStudioRightPanel(copilot, summary, assist)).toBe(expected)
  })
  it('leaves reading and writing space at desktop sizes and overlays narrow panels', () => {
    const reading = getStudioWorkspaceLayout(1280, true, 256, 700, false)
    expect(reading.assistantOverlay).toBe(false)
    expect(1280 - reading.visibleChapterWidth - reading.visibleDrawerWidth).toBe(420)
    expect(getStudioWorkspaceLayout(1280, true, 400, 360, true).assistantOverlay).toBe(true)
    const narrow = getStudioWorkspaceLayout(390, true, 400, 700, false)
    expect(narrow).toMatchObject({ navigationOverlay: true, assistantOverlay: true, visibleChapterWidth: 342, visibleDrawerWidth: 358 })
  })
})
