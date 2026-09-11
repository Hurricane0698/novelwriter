// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import type { SceneId } from '@/components/home/screenshotManifest'
import type { UiMessageKey } from '@/lib/uiMessages'

type HomeNarrativeActDefinition = {
  sceneId: SceneId
  stepLabel: string
  eyebrowKey: UiMessageKey
  titleKey: UiMessageKey
  descriptionKey: UiMessageKey
}

export const homeNarrativeActs: readonly HomeNarrativeActDefinition[] = [
  {
    sceneId: 'import',
    stepLabel: '01',
    eyebrowKey: 'home.narrative.act1.eyebrow',
    titleKey: 'home.narrative.act1.title',
    descriptionKey: 'home.narrative.act1.description',
  },
  {
    sceneId: 'settings',
    stepLabel: '02',
    eyebrowKey: 'home.narrative.act2.eyebrow',
    titleKey: 'home.narrative.act2.title',
    descriptionKey: 'home.narrative.act2.description',
  },
  {
    sceneId: 'governance',
    stepLabel: '03',
    eyebrowKey: 'home.narrative.act3.eyebrow',
    titleKey: 'home.narrative.act3.title',
    descriptionKey: 'home.narrative.act3.description',
  },
  {
    sceneId: 'copilot',
    stepLabel: '04',
    eyebrowKey: 'home.narrative.act4.eyebrow',
    titleKey: 'home.narrative.act4.title',
    descriptionKey: 'home.narrative.act4.description',
  },
  {
    sceneId: 'continuation',
    stepLabel: '05',
    eyebrowKey: 'home.narrative.act5.eyebrow',
    titleKey: 'home.narrative.act5.title',
    descriptionKey: 'home.narrative.act5.description',
  },
] as const

export const HOME_NARRATIVE_ACT_COUNT = homeNarrativeActs.length

type HomeFeatureRowDefinition = {
  id: 'studio' | 'atlas' | 'copilot'
  eyebrowKey: UiMessageKey
  titleKey: UiMessageKey
  descriptionKey: UiMessageKey
  altKey: UiMessageKey
  screenshot: string
  windowLabelKey: UiMessageKey
}

export const homeFeatureRows: readonly HomeFeatureRowDefinition[] = [
  {
    id: 'studio',
    eyebrowKey: 'home.feature.studio.eyebrow',
    titleKey: 'home.feature.studio.title',
    descriptionKey: 'home.feature.studio.description',
    altKey: 'home.feature.studio.alt',
    screenshot: homeScreenshotAssets.studioWorkspace,
    windowLabelKey: 'home.stage.window.studio',
  },
  {
    id: 'atlas',
    eyebrowKey: 'home.feature.atlas.eyebrow',
    titleKey: 'home.feature.atlas.title',
    descriptionKey: 'home.feature.atlas.description',
    altKey: 'home.feature.atlas.alt',
    screenshot: homeScreenshotAssets.atlasWorkspace,
    windowLabelKey: 'home.stage.window.atlas',
  },
  {
    id: 'copilot',
    eyebrowKey: 'home.feature.copilot.eyebrow',
    titleKey: 'home.feature.copilot.title',
    descriptionKey: 'home.feature.copilot.description',
    altKey: 'home.feature.copilot.alt',
    screenshot: homeScreenshotAssets.copilotChat,
    windowLabelKey: 'home.stage.window.copilot',
  },
] as const

