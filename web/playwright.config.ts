import { defineConfig, devices } from '@playwright/test'

const shared = {
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
} as const

/** Mock E2E — strict intercept, no real backend needed */
export const mockConfig = defineConfig({
  ...shared,
  testDir: './e2e/mock',
  reporter: [['html', { outputFolder: 'playwright-report/mock' }]],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
})

/** Integration E2E — real backend at :8000, frontend at :5173 */
export const integrationConfig = defineConfig({
  ...shared,
  testDir: './e2e/integration',
  reporter: [['html', { outputFolder: 'playwright-report/integration' }]],
  webServer: [
    {
      // Prefer same-origin `/api/*` via Vite dev proxy to avoid CORS variance in selfhost mode.
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'cd .. && sh -c "if [ -x .venv/bin/python ]; then .venv/bin/python -m uvicorn app.main:app --port 8000; else python -m uvicorn app.main:app --port 8000; fi"',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
    },
  ],
})

export default mockConfig
