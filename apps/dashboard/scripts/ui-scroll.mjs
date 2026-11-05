
import { chromium } from 'playwright';
const out = "F:\\Desktop\\Documents\\Codex\\Stratide\\issue85-worktree\\state\\ui-shots";
const token = "282b083feace7de66b91377d9eb92682a9447ee89fbcbd947e9cd4d7d1386338";
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto('http://127.0.0.1:8710/#settings/runtime?rt=' + token, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);
const metrics = await page.evaluate(() => {
  const scrollers = [...document.querySelectorAll('*')].filter(e => {
    const s = getComputedStyle(e);
    return e.scrollHeight > e.clientHeight + 40 && /auto|scroll/.test(s.overflowY);
  }).map(e => ({ tag: e.tagName, cls: e.className, sh: e.scrollHeight, ch: e.clientHeight }));
  return { doc: document.scrollingElement.scrollHeight, win: innerHeight, scrollers };
});
console.log(JSON.stringify(metrics));
await page.evaluate(() => {
  const el = [...document.querySelectorAll('*')].find(e => {
    const s = getComputedStyle(e);
    return e.scrollHeight > e.clientHeight + 40 && /auto|scroll/.test(s.overflowY);
  });
  if (el) el.scrollTop = el.scrollHeight;
});
await page.waitForTimeout(600);
await page.screenshot({ path: out + '/v3-runtime-bottom.png' });
await browser.close();
