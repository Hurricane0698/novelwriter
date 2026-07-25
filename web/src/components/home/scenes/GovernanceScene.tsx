// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { ScreenshotStageAsset } from '@/components/home/ScreenshotStageAsset'
import { sceneManifest } from '@/components/home/screenshotManifest'
import { useUiLocale } from '@/contexts/UiLocaleContext'

/**
 * GovernanceScene — Act 3: Atlas / 审核
 *
 * Narrative copy on the left already explains the review contract.
 * The stage should show one continuous real Atlas review surface instead of
 * layering marketing-only metric cards on top of the product evidence.
 */
export default function GovernanceScene() {
  const { t } = useUiLocale()

  return (
    <div className="h-full bg-[radial-gradient(circle_at_top_left,#eef4ff_0%,#f8faff_42%,#ffffff_82%)] p-3 sm:p-4">
      <div className="h-full overflow-hidden rounded-[24px] border border-indigo-100/90 bg-[#f8faff] shadow-[0_16px_36px_rgba(15,23,42,0.04)]">
        <ScreenshotStageAsset
          src={sceneManifest.governance.screenshot}
          alt={t(sceneManifest.governance.labelKey)}
          objectPosition="left top"
          scale={1}
        />
      </div>
    </div>
  )
}
