// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { homeScreenshotAssets } from '@/components/home/homeScreenshotAssets'
import type { SceneId } from '@/components/home/screenshotManifest'
import type { UiMessageKey } from '@/lib/uiMessages'

export type HomeNarrativeVariant = 'editorial' | 'thread'

type HomeNarrativeActDefinition = {
  sceneId: SceneId
  stepLabel: string
  variant: HomeNarrativeVariant
  eyebrowKey: UiMessageKey
  titleKey: UiMessageKey
  descriptionKey: UiMessageKey
  bullets: readonly [UiMessageKey, UiMessageKey, UiMessageKey]
}

export const homeNarrativeActs: readonly HomeNarrativeActDefinition[] = [
  {
    sceneId: 'import',
    stepLabel: '01',
    variant: 'editorial',
    eyebrowKey: 'home.narrative.act1.eyebrow',
    titleKey: 'home.narrative.act1.title',
    descriptionKey: 'home.narrative.act1.description',
    bullets: [
      'home.narrative.act1.bullet1',
      'home.narrative.act1.bullet2',
      'home.narrative.act1.bullet3',
    ],
  },
  {
    sceneId: 'settings',
    stepLabel: '02',
    variant: 'thread',
    eyebrowKey: 'home.narrative.act2.eyebrow',
    titleKey: 'home.narrative.act2.title',
    descriptionKey: 'home.narrative.act2.description',
    bullets: [
      'home.narrative.act2.bullet1',
      'home.narrative.act2.bullet2',
      'home.narrative.act2.bullet3',
    ],
  },
  {
    sceneId: 'governance',
    stepLabel: '03',
    variant: 'editorial',
    eyebrowKey: 'home.narrative.act3.eyebrow',
    titleKey: 'home.narrative.act3.title',
    descriptionKey: 'home.narrative.act3.description',
    bullets: [
      'home.narrative.act3.bullet1',
      'home.narrative.act3.bullet2',
      'home.narrative.act3.bullet3',
    ],
  },
  {
    sceneId: 'copilot',
    stepLabel: '04',
    variant: 'thread',
    eyebrowKey: 'home.narrative.act4.eyebrow',
    titleKey: 'home.narrative.act4.title',
    descriptionKey: 'home.narrative.act4.description',
    bullets: [
      'home.narrative.act4.bullet1',
      'home.narrative.act4.bullet2',
      'home.narrative.act4.bullet3',
    ],
  },
  {
    sceneId: 'continuation',
    stepLabel: '05',
    variant: 'editorial',
    eyebrowKey: 'home.narrative.act5.eyebrow',
    titleKey: 'home.narrative.act5.title',
    descriptionKey: 'home.narrative.act5.description',
    bullets: [
      'home.narrative.act5.bullet1',
      'home.narrative.act5.bullet2',
      'home.narrative.act5.bullet3',
    ],
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
  accentHex: string
  objectPosition: string
  scale: number
  imageClassName?: string
  imageRight: boolean
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
    accentHex: '#5b6bf0',
    objectPosition: 'center center',
    scale: 1,
    imageClassName: 'object-contain bg-white',
    imageRight: false,
  },
  {
    id: 'atlas',
    eyebrowKey: 'home.feature.atlas.eyebrow',
    titleKey: 'home.feature.atlas.title',
    descriptionKey: 'home.feature.atlas.description',
    altKey: 'home.feature.atlas.alt',
    screenshot: homeScreenshotAssets.atlasWorkspace,
    windowLabelKey: 'home.stage.window.atlas',
    accentHex: '#4a7de8',
    objectPosition: 'center center',
    scale: 1,
    imageClassName: 'object-contain bg-white',
    imageRight: true,
  },
  {
    id: 'copilot',
    eyebrowKey: 'home.feature.copilot.eyebrow',
    titleKey: 'home.feature.copilot.title',
    descriptionKey: 'home.feature.copilot.description',
    altKey: 'home.feature.copilot.alt',
    screenshot: homeScreenshotAssets.copilotChat,
    windowLabelKey: 'home.stage.window.copilot',
    accentHex: '#7a5cf0',
    objectPosition: '50% 0%',
    scale: 1.03,
    imageRight: false,
  },
] as const

