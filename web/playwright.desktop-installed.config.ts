import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/desktop-installed',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  // First launch on 2-vCPU runners can crawl for ~3 minutes while WebView2
  // first-run, Defender scanning, and the queued demo index build compete;
  // the budget covers that storm plus the normal flow, below the outer
  // process watchdog in smoke_windows_desktop_installer.ps1.
  timeout: 360_000,
  expect: {
    // Individual first paints during the storm were observed at 30-70s;
    // per-wait budgets stay generous while the 360s test budget caps the
    // aggregate.
    timeout: 120_000,
  },
  reporter: [['line']],
  outputDir: 'test-results/desktop-installed',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:8000',
    actionTimeout: 120_000,
    navigationTimeout: 120_000,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
