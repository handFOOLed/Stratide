import { defineConfig } from '@playwright/test';

const scenarios = [['synthetic',8711],['empty',8712],['invalid',8713],['missing-nav',8714]];
if (process.env.STRATIDE_HISTORICAL_REPORT) scenarios.push(['historical',8715]);
export default defineConfig({
  testDir: './tests', testMatch: '*.browser.js', workers: 1,
  timeout: 30_000, use: { browserName: 'chromium', channel: process.env.STRATIDE_BROWSER_CHANNEL || 'msedge', headless: true, baseURL: 'http://127.0.0.1:8711', viewport: { width: 1366, height: 900 }, screenshot: 'only-on-failure' },
  webServer: scenarios.map(([scenario,port]) => ({ command: `node tests/serve-fixture.mjs ${scenario} ${port}`, url: `http://127.0.0.1:${port}/api/health`, reuseExistingServer: false, timeout: 15_000 })),
});
