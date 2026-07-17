import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/desktop-installed',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 210_000,
  expect: {
    timeout: 30_000,
  },
  reporter: [['line']],
  outputDir: 'test-results/desktop-installed',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:8000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
