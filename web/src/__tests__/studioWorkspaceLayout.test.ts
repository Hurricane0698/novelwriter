import { describe, expect, it } from 'vitest'
import { getStudioWorkspaceLayout } from '@/components/studio/studioWorkspaceLayout'

describe('workspace panels', () => {
  it('leaves reading and writing space at desktop sizes and overlays narrow panels', () => {
    const reading = getStudioWorkspaceLayout(1280, true, 256, 700, false)
    expect(reading.assistantOverlay).toBe(false)
    expect(1280 - reading.visibleChapterWidth - reading.visibleDrawerWidth).toBeGreaterThanOrEqual(400)
    expect(getStudioWorkspaceLayout(1280, true, 400, 360, true).assistantOverlay).toBe(true)
    const narrow = getStudioWorkspaceLayout(390, true, 400, 700, false)
    expect(narrow).toMatchObject({ navigationOverlay: true, assistantOverlay: true })
  })
})
