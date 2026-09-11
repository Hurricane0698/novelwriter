// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

const HOME_SCREENSHOT_PUBLIC_DIR = '/screenshots/home' as const
const HOME_SCREENSHOT_BUILD_ID = __NOVWR_BUILD_ID__

const homeScreenshotPreloadCache = new Map<string, Promise<void>>()

function buildVersionedHomeScreenshotUrl(fileName: string): string {
  const search = new URLSearchParams({ v: HOME_SCREENSHOT_BUILD_ID }).toString()
  return `${HOME_SCREENSHOT_PUBLIC_DIR}/${fileName}?${search}`
}

function preloadImage(src: string): Promise<void> {
  const cached = homeScreenshotPreloadCache.get(src)
  if (cached) return cached

  const promise = new Promise<void>((resolve) => {
    if (typeof Image === 'undefined') {
      resolve()
      return
    }

    const image = new Image()
    image.decoding = 'async'
    image.onload = () => resolve()
    image.onerror = () => resolve()
    image.src = src
  })

  homeScreenshotPreloadCache.set(src, promise)
  return promise
}

export const homeScreenshotAssets = {
  // ── Workflow scenes (1–5) ──
  library: buildVersionedHomeScreenshotUrl('library-light.jpg'),
  settingsGenerate: buildVersionedHomeScreenshotUrl('settings-light.jpg'),
  atlasReview: buildVersionedHomeScreenshotUrl('review-light.jpg'),
  copilotChat: buildVersionedHomeScreenshotUrl('copilot-light.jpg'),
  studioWrite: buildVersionedHomeScreenshotUrl('continuation-light.jpg'),
  // ── Dedicated non-workflow product surfaces ──
  studioWorkspace: buildVersionedHomeScreenshotUrl('studio-light.jpg'),
  atlasWorkspace: buildVersionedHomeScreenshotUrl('atlas-light.jpg'),
} as const

export function getHomeScreenshotForTheme(src: string, theme: 'light' | 'dark'): string {
  return theme === 'dark' ? src.replace('-light.jpg', '-dark.jpg') : src
}

export const homeProductStageScreenshotPublicPaths = [
  homeScreenshotAssets.library,
  homeScreenshotAssets.settingsGenerate,
  homeScreenshotAssets.atlasReview,
  homeScreenshotAssets.copilotChat,
  homeScreenshotAssets.studioWrite,
  homeScreenshotAssets.studioWorkspace,
  homeScreenshotAssets.atlasWorkspace,
].flatMap((src) => [src, getHomeScreenshotForTheme(src, 'dark')])

export async function preloadHomeProductStageScreenshots(): Promise<void> {
  await Promise.all(homeProductStageScreenshotPublicPaths.map((src) => preloadImage(src)))
}
