// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: MIT

/**
 * Playwright script to capture homepage product-stage screenshots.
 *
 * Usage:
 *   cd web && npx playwright test scripts/capture-homepage-screenshots.ts --config playwright.capture.config.ts
 *
 * Prerequisites:
 *   - Frontend dev server running at localhost:5173
 *   - No backend needed (homepage is static)
 *
 * Output:
 *   - web/public/screenshots/home/{assetFile}.png  — assets used by the homepage
 *   - artifacts/playwright_ui_verify/home_*.png — visual audit captures
 */

import { test } from '@playwright/test'
import {
  captureHomepageAuditScreenshots,
  captureHomepageProductStageScreenshots,
  openHomepageCaptureTarget,
  prepareHomepageCapturePage,
} from './homepageScreenshotCapture'

test.describe('Homepage screenshot capture', () => {
  test.beforeEach(async ({ page }) => {
    await prepareHomepageCapturePage(page)
  })

  test('capture audit screenshots — top, mid, bottom', async ({ page }) => {
    await openHomepageCaptureTarget(page)
    await captureHomepageAuditScreenshots(page)
  })

  test('capture homepage screenshot assets', async ({ page }) => {
    await openHomepageCaptureTarget(page)
    await captureHomepageProductStageScreenshots(page)
  })
})
