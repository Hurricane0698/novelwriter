// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: MIT

import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type Locator, type Page } from '@playwright/test'

export const HOMEPAGE_CAPTURE_BASE_URL = 'http://localhost:5173'
export const HOMEPAGE_PRODUCT_STAGE_CAPTURE_TARGETS = [
  { actIndex: 0, outputFile: '1.png' },
  { actIndex: 1, outputFile: '2.png' },
  { actIndex: 2, outputFile: '3.png' },
  { actIndex: 3, outputFile: '4.png' },
  { actIndex: 4, outputFile: '5.png' },
] as const

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
export const HOMEPAGE_CAPTURE_SCREENSHOT_DIR = resolve(SCRIPT_DIR, '../public/screenshots/home')
export const HOMEPAGE_CAPTURE_AUDIT_DIR = resolve(SCRIPT_DIR, '../../artifacts/playwright_ui_verify')

function ensureCaptureDirs() {
  mkdirSync(HOMEPAGE_CAPTURE_SCREENSHOT_DIR, { recursive: true })
  mkdirSync(HOMEPAGE_CAPTURE_AUDIT_DIR, { recursive: true })
}

async function getNarrativeAbsoluteTop(page: Page, narrative: Locator) {
  const narrativeBox = await narrative.boundingBox()
  if (!narrativeBox) return null

  const scrollY = await page.evaluate(() => window.scrollY)
  return {
    top: narrativeBox.y + scrollY,
    height: narrativeBox.height,
  }
}

export async function prepareHomepageCapturePage(page: Page) {
  ensureCaptureDirs()
  await page.addInitScript(() => {
    localStorage.setItem('novwr_theme', 'light')
    document.documentElement.classList.add('light')
  })
  await page.setViewportSize({ width: 1440, height: 900 })
}

export async function openHomepageCaptureTarget(page: Page) {
  await page.goto(HOMEPAGE_CAPTURE_BASE_URL, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
}

export async function captureHomepageAuditScreenshots(page: Page) {
  await page.screenshot({
    path: resolve(HOMEPAGE_CAPTURE_AUDIT_DIR, 'home_top.png'),
    fullPage: false,
  })

  const narrative = page.locator('#narrative')
  await narrative.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)

  for (let i = 0; i < 5; i++) {
    const scrollY = 600 + i * 800
    await page.evaluate((y) => window.scrollTo(0, y), scrollY)
    await page.waitForTimeout(300)
    await page.screenshot({
      path: resolve(HOMEPAGE_CAPTURE_AUDIT_DIR, `home_mid_act${i + 1}.png`),
      fullPage: false,
    })
  }

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await page.waitForTimeout(500)
  await page.screenshot({
    path: resolve(HOMEPAGE_CAPTURE_AUDIT_DIR, 'home_bottom.png'),
    fullPage: false,
  })

  await page.screenshot({
    path: resolve(HOMEPAGE_CAPTURE_AUDIT_DIR, 'home_full.png'),
    fullPage: true,
  })
}

export async function captureHomepageProductStageScreenshots(page: Page) {
  const narrative = page.locator('#narrative')
  await expect(narrative).toBeVisible()

  const stage = page.locator('#narrative .sticky').first()

  for (const target of HOMEPAGE_PRODUCT_STAGE_CAPTURE_TARGETS) {
    const narrativeMetrics = await getNarrativeAbsoluteTop(page, narrative)
    if (!narrativeMetrics) continue

    const targetScroll = narrativeMetrics.top
      + (narrativeMetrics.height * (target.actIndex + 0.5)) / HOMEPAGE_PRODUCT_STAGE_CAPTURE_TARGETS.length
    await page.evaluate((y) => window.scrollTo(0, y), targetScroll)
    await page.waitForTimeout(600)

    await expect(stage).toBeVisible()
    await stage.screenshot({
      path: resolve(HOMEPAGE_CAPTURE_SCREENSHOT_DIR, target.outputFile),
    })
  }
}
