import { defineConfig } from '@playwright/test'

// Browser acceptance for UI-05/UI-06. The API is mocked per test from e2e/fixtures/ (test fixtures,
// not results). Set CHROMIUM_PATH to use a system Chromium instead of `npx playwright install`.
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  timeout: 180_000, // axe over the full aggregate table on screen F is slow
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  webServer: {
    command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
