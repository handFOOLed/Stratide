import { defineConfig } from '@playwright/test';

const scenarios = [
  ['synthetic', 8731],
  ['empty', 8732],
  ['invalid', 8733],
  ['missing-nav', 8734],
  ['agent', 8736],
  ['agreement', 8737],
];
if (process.env.STRATIDE_HISTORICAL_REPORT) scenarios.push(['historical', 8735]);

export default defineConfig({
  testDir: './tests',
  testMatch: '*.browser.js',
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]] : [['line']],
  use: {
    browserName: 'chromium',
    channel: process.env.STRATIDE_BROWSER_CHANNEL || 'msedge',
    headless: true,
    baseURL: 'http://127.0.0.1:8731',
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: scenarios.map(([scenario, port]) => ({
    command: `node tests/serve-fixture.mjs ${scenario} ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 30_000,
  })),
});
