import { defineConfig } from '@playwright/test';
import path from 'node:path';

export default defineConfig({
  testDir: '.',
  testMatch: 'market.browser.js',
  workers: 1,
  timeout: 30_000,
  use: {browserName:'chromium',channel:'msedge',headless:true,baseURL:'http://127.0.0.1:8737'},
  webServer: {
    command: 'node tests/serve-fixture.mjs synthetic 8737',
    cwd: path.resolve(import.meta.dirname, '..'),
    url: 'http://127.0.0.1:8737/api/health',
    reuseExistingServer: false,
  },
});
