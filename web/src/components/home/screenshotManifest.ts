// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import type { UiMessageKey } from '@/lib/uiMessages'

export type SceneId = 'import' | 'settings' | 'governance' | 'copilot' | 'continuation'

type SceneEntry = {
  id: SceneId
  windowLabelKey: UiMessageKey
  labelKey: UiMessageKey
  screenshot: string
  mobilePosition: string
  mobileScale: number
  tone: 'studio' | 'atlas' | 'copilot'
}

export const sceneManifest: Record<SceneId, SceneEntry> = {
  import: {
    id: 'import',
    windowLabelKey: 'home.stage.window.library',
    labelKey: 'home.stage.caption.import',
    tone: 'studio',
    screenshot: homeScreenshotAssets.library,
    mobilePosition: 'left top',
    mobileScale: 1.3,
  },
  settings: {
    id: 'settings',
    windowLabelKey: 'home.stage.window.atlas',
    labelKey: 'home.stage.caption.settings',
    tone: 'atlas',
    screenshot: homeScreenshotAssets.settingsGenerate,
    mobilePosition: 'center center',
    mobileScale: 1.2,
  },
  governance: {
    id: 'governance',
    windowLabelKey: 'home.stage.window.atlas',
    labelKey: 'home.stage.caption.governance',
    tone: 'atlas',
    screenshot: homeScreenshotAssets.atlasReview,
    mobilePosition: 'right center',
    mobileScale: 1.4,
  },
  copilot: {
    id: 'copilot',
    windowLabelKey: 'home.stage.window.copilot',
    labelKey: 'home.stage.caption.copilot',
    tone: 'copilot',
    screenshot: homeScreenshotAssets.copilotChat,
    mobilePosition: 'right bottom',
    mobileScale: 1.8,
  },
  continuation: {
    id: 'continuation',
    windowLabelKey: 'home.stage.window.studio',
    labelKey: 'home.stage.caption.continuation',
    tone: 'studio',
    screenshot: homeScreenshotAssets.studioWrite,
    mobilePosition: 'right bottom',
    mobileScale: 1.8,
  },
}
