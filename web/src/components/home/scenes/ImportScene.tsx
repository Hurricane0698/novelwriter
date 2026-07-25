// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { useUiLocale } from '@/contexts/UiLocaleContext'

/**
 * ImportScene — Act 1: Library / 导入
 *
 * Lead with the left side of the real library surface so the visitor can read
 * the page title plus the contrast between a fresh 0-chapter project and an
 * imported 1000+-chapter novel at a glance.
 */
export default function ImportScene() {
  const { t } = useUiLocale()

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(circle_at_top_left,#eef1ff_0%,#fafbff_38%,#ffffff_78%)]">
      <ScreenshotStageAsset
        src={sceneManifest.import.screenshot}
        alt={t(sceneManifest.import.labelKey)}
        objectPosition="left top"
        scale={1}
      />
    </div>
  )
}
