
import { chromium } from 'playwright';
const out = "F:\\Desktop\\Documents\\Codex\\Stratide\\issue85-worktree\\state\\ui-shots";
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto('http://127.0.0.1:8710/#overview', { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
if (await page.getByRole('button', { name: '同意并继续' }).count()) {
  await page.getByRole('button', { name: '同意并继续' }).click();
  await page.waitForTimeout(2200);
}
for (const [name, hash] of [['v6-agent','#agents'],['v6-ai','#settings/ai'],['v6-runtime','#settings/runtime']]) {
  await page.evaluate((h) => { window.location.hash = h; }, hash);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: out + '/' + name + '.png' });
  console.log(name);
}
// scrolled runtime for the progress bar
await page.evaluate(() => {
  const el = [...document.querySelectorAll('*')].find(e => {
    const s = getComputedStyle(e);
    return e.scrollHeight > e.clientHeight + 40 && /auto|scroll/.test(s.overflowY);
  });
  if (el) el.scrollTop = el.scrollHeight;
});
await page.waitForTimeout(700);
await page.screenshot({ path: out + '/v6-runtime-bottom.png' });
console.log('v6-runtime-bottom');
await browser.close();
