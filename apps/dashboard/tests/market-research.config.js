import { defineConfig } from '@playwright/test';
import path from 'node:path';
export default defineConfig({
  testDir: '.', testMatch: 'market-research.browser.js', workers: 1, timeout: 40_000,
  use: {browserName:'chromium',channel:'msedge',headless:true,baseURL:'http://127.0.0.1:8739'},
  webServer: {command:'node tests/serve-fixture.mjs agent 8739',cwd:path.resolve(import.meta.dirname,'..'),
    url:'http://127.0.0.1:8739/api/health',reuseExistingServer:false},
});
