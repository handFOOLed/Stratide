
import { chromium } from 'playwright';
const out = "F:\\Desktop\\Documents\\Codex\\Stratide\\issue85-worktree\\state\\ui-shots";
const token = "282b083feace7de66b91377d9eb92682a9447ee89fbcbd947e9cd4d7d1386338";
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto('http://127.0.0.1:8710/#overview', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.screenshot({ path: out + '/v4-agreement.png' });
console.log('agreement shot');
await page.getByRole('button', { name: '同意并继续' }).click();
await page.waitForTimeout(2500);
for (const [name, hash] of [['v4-overview','#overview'],['v4-settings-ai','#settings/ai'],['v4-agent','#agents'],['v4-notifications','#notifications'],['v4-runtime','#settings/runtime']]) {
  await page.evaluate((h) => { window.location.hash = h + '?rt=' + window.__rt; }, hash).catch(() => {});
  await page.evaluate((args) => { window.location.hash = args[0] + '?rt=' + args[1]; }, [hash, token]);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: out + '/' + name + '.png' });
  console.log(name);
}
await browser.close();
