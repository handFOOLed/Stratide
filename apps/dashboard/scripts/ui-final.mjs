
import { chromium } from 'playwright';
const out = "F:\\Desktop\\Documents\\Codex\\Stratide\\issue85-worktree\\state\\ui-shots";
const token = "282b083feace7de66b91377d9eb92682a9447ee89fbcbd947e9cd4d7d1386338";
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
async function shot(name, url) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: out + '/' + name + '.png', fullPage: true });
  console.log(name, 'errors:', JSON.stringify(errors));
  await page.close();
}
const base = 'http://127.0.0.1:8710/';
await shot('v3-ai', base + '#settings/ai?rt=' + token);
await shot('v3-runtime', base + '#settings/runtime?rt=' + token);
await browser.close();
