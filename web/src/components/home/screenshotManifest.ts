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
  accentHex: string
}

export const sceneManifest: Record<SceneId, SceneEntry> = {
  import: {
    id: 'import',
    windowLabelKey: 'home.stage.window.library',
    labelKey: 'home.stage.caption.import',
    accentHex: '#5b6bf0',
    screenshot: homeScreenshotAssets.library,
  },
  settings: {
    id: 'settings',
    windowLabelKey: 'home.stage.window.atlas',
    labelKey: 'home.stage.caption.settings',
    accentHex: '#4a7de8',
    screenshot: homeScreenshotAssets.settingsGenerate,
  },
  governance: {
    id: 'governance',
    windowLabelKey: 'home.stage.window.atlas',
    labelKey: 'home.stage.caption.governance',
    accentHex: '#4a7de8',
    screenshot: homeScreenshotAssets.atlasReview,
  },
  copilot: {
    id: 'copilot',
    windowLabelKey: 'home.stage.window.copilot',
    labelKey: 'home.stage.caption.copilot',
    accentHex: '#7a5cf0',
    screenshot: homeScreenshotAssets.copilotChat,
  },
  continuation: {
    id: 'continuation',
    windowLabelKey: 'home.stage.window.studio',
    labelKey: 'home.stage.caption.continuation',
    accentHex: '#5b6bf0',
    screenshot: homeScreenshotAssets.studioWrite,
  },
}
