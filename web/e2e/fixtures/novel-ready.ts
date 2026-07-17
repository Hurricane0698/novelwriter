import { expect, type Page } from '@playwright/test'

declare global {
  interface Window {
    __novwrTestVisibilitySeen?: Record<string, boolean>
  }
}

export async function dismissOnboardingAndReturnToStudio(
  page: Page,
  novelId: number,
) {
  await page.getByTestId('world-onboarding-dismiss').click()
  await expect(page).toHaveURL(new RegExp(`/world/${novelId}`), { timeout: 15_000 })
  await page.getByRole('button', { name: '返回工作台' }).click()
  await expect(page).toHaveURL(new RegExp(`/novel/${novelId}$`), { timeout: 15_000 })
}

export async function waitForInitialNovelReady(
  page: Page,
  novelId: number,
  opts?: {
    requireOnboarding?: boolean
    dismissOnboarding?: boolean
    /** Per-wait budget for readiness signals; installed runs raise it to ride out the first-launch storm. */
    readyTimeoutMs?: number
  },
) {
  const readyTimeoutMs = opts?.readyTimeoutMs ?? 30_000
  const preparationGate = page.getByTestId('studio-preparation-gate')
  const onboarding = page.getByTestId('world-onboarding')
  const chapterList = page.getByTestId('studio-rail-chapters')
  const chapterBtn = chapterList.getByRole('button', { name: /第\s*1\s*章/ })

  await Promise.any([
    preparationGate.waitFor({ state: 'visible', timeout: readyTimeoutMs }),
    onboarding.waitFor({ state: 'visible', timeout: readyTimeoutMs }),
    chapterBtn.waitFor({ state: 'visible', timeout: readyTimeoutMs }),
  ])

  if (await preparationGate.isVisible()) {
    await expect(preparationGate).toBeHidden({ timeout: 120_000 })
    await Promise.any([
      onboarding.waitFor({ state: 'visible', timeout: readyTimeoutMs }),
      chapterBtn.waitFor({ state: 'visible', timeout: readyTimeoutMs }),
    ])
  }

  if (opts?.requireOnboarding) {
    await expect(onboarding).toBeVisible({ timeout: readyTimeoutMs })
    return
  }

  if (opts?.dismissOnboarding && await onboarding.isVisible()) {
    await dismissOnboardingAndReturnToStudio(page, novelId)
  }
}

export async function installTestIdVisibilityProbe(
  page: Page,
  key: string,
  testId: string,
) {
  await page.addInitScript(({ probeKey, probeTestId }) => {
    const marker = '__novwrVisibilityProbeInstalled'
    const globalWindow = window as Window & { [marker]?: Record<string, boolean> }
    globalWindow.__novwrTestVisibilitySeen ??= {}

    if (globalWindow[marker]?.[probeKey]) return
    globalWindow[marker] ??= {}
    globalWindow[marker]![probeKey] = true

    const markIfVisible = () => {
      const element = document.querySelector<HTMLElement>(`[data-testid="${probeTestId}"]`)
      if (!element) return

      const style = window.getComputedStyle(element)
      const visible = (
        style.display !== 'none'
        && style.visibility !== 'hidden'
        && !element.hasAttribute('hidden')
        && element.getClientRects().length > 0
      )
      if (visible) {
        window.__novwrTestVisibilitySeen![probeKey] = true
      }
    }

    markIfVisible()
    const observer = new MutationObserver(markIfVisible)
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
    })
  }, { probeKey: key, probeTestId: testId })
}

export async function wasTestIdSeen(page: Page, key: string): Promise<boolean> {
  return page.evaluate((probeKey) => window.__novwrTestVisibilitySeen?.[probeKey] === true, key)
}
