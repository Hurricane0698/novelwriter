// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { useUiLocale } from '@/contexts/UiLocaleContext'

/**
 * ContinuationScene — Act 5: Studio / 续写
 *
 * The proof beat here is the real Studio continuation surface itself:
 * generated result, text-quality check, and injection summary all visible in
 * one continuous screenshot. Avoid extra HUD overlays that compete with or
 * cover the bottom review evidence.
 */
export default function ContinuationScene() {
  const { t } = useUiLocale()

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(circle_at_bottom,rgba(91,107,240,0.06)_0%,#ffffff_62%)]">
      <ScreenshotStageAsset
        src={sceneManifest.continuation.screenshot}
        alt={t(sceneManifest.continuation.labelKey)}
        objectPosition="left top"
        scale={1}
      />
    </div>
  )
}
