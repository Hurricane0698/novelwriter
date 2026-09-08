import { describe, expect, it, vi, afterEach } from 'vitest'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('homeScreenshotAssets', () => {
  it('preloads each stage screenshot source only once across repeated warmups', async () => {
    const assignedSources: string[] = []

    class MockImage {
      decoding = ''
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(value: string) {
        assignedSources.push(value)
        queueMicrotask(() => this.onload?.())
      }
    }

    vi.stubGlobal('Image', MockImage)

    const {
      homeProductStageScreenshotPublicPaths,
      preloadHomeProductStageScreenshots,
    } = await import('@/components/home/homeScreenshotAssets')

    await preloadHomeProductStageScreenshots()
    await preloadHomeProductStageScreenshots()

    expect(assignedSources).toEqual([...homeProductStageScreenshotPublicPaths])
  })
})
