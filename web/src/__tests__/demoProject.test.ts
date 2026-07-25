import { describe, expect, it } from 'vitest'
import { buildDemoStudioPath, findSeededDemoNovel, isSeededDemoNovel } from '@/lib/demoProject'

describe('demoProject helpers', () => {
  it('detects the seeded demo novel by backend flag only', () => {
    expect(isSeededDemoNovel({ is_seeded_demo: true })).toBe(true)
    expect(isSeededDemoNovel({ is_seeded_demo: false })).toBe(false)
    expect(isSeededDemoNovel(null)).toBe(false)
  })

  it('finds the seeded demo novel from a novel list', () => {
    expect(findSeededDemoNovel([
      { id: 1, is_seeded_demo: false },
      { id: 2, is_seeded_demo: true },
    ])).toMatchObject({ id: 2, is_seeded_demo: true })
    expect(findSeededDemoNovel([{ id: 1, is_seeded_demo: false }])).toBeNull()
  })

  it('builds the demo studio path with optional guide reopening', () => {
    expect(buildDemoStudioPath(7)).toBe('/novel/7')
    expect(buildDemoStudioPath(7, { forceGuideOpen: true })).toBe('/novel/7?demoGuide=open')
  })
})
