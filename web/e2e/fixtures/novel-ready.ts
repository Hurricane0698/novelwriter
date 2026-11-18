import { expect, type Page } from '@playwright/test'

export async function waitForInitialNovelReady(page: Page, timeout = 120_000) {
  const firstChapter = page.getByTestId('studio-rail-chapters').getByRole('button', { name: /第\s*1\s*章/ })
  await expect(firstChapter).toBeVisible({ timeout })
}
