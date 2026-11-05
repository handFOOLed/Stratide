import { test, expect } from '@playwright/test';

/**
 * 全局外壳 / 术语巡检 / 响应式 / 首次使用页。
 * synthetic 场景 8731，首次使用协议场景 8737。
 */
const BASE = 'http://127.0.0.1:8731';
const AGREEMENT = 'http://127.0.0.1:8737';

const BANNED = [
  'not_configured', 'PIT', 'daily.open', 'EOD', 'Supervisor', 'Owner', 'Agent', 'Paper',
  '见技术详情', '占位', '不调用模型', '不发起推理', 'snapshot_id', 'report_sha256', 'input_sha256',
  'ledger_head', 'provider_hash', 'frozen_version', 'deployment_id', 'strategy_id', 'hash',
  'READY', 'BLOCKED', 'CONFIGURED', 'MISSING', 'queued', 'completed', 'cancelled', '已配置',
  '已安装', '已初始化', '已连接', '服务在线', '风控锁', '源日', '逐日核对', '隐含持仓',
];
const ENUM_WORDS = ['queued', 'running', 'completed', 'failed', 'cancelled', 'blocked', 'outcome_uncertain', 'READY', 'CONFIGURED', 'NOT_CONFIGURED'];
const PAGES = [
  ['#overview', '总览'],
  ['#history/fills', '交易记录'],
  ['#history/orders', '交易记录'],
  ['#history/daily', '交易记录'],
  ['#agents', 'AI 研究'],
  ['#notifications', '通知'],
  ['#settings', '设置'],
  ['#settings/ai', '设置'],
  ['#settings/data', '设置'],
  ['#settings/runtime', '设置'],
  ['#settings/about', '设置'],
];

async function mainRegionText(page) {
  return page.evaluate(() => {
    const parts = [];
    const walk = (node) => {
      if (node.nodeType === Node.TEXT_NODE) { parts.push(node.textContent || ''); return; }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const el = node;
      if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'NOSCRIPT') return;
      if (el.matches('details.diagnostics')) return;
      for (const child of el.childNodes) walk(child);
    };
    walk(document.querySelector('.page-frame') || document.body);
    return parts.join(' ');
  });
}

test('主导航与设置分类：五个入口、当前页高亮、键盘可切换', async ({ page }) => {
  await page.goto(BASE + '/#overview');
  const nav = page.locator('.sidebar .nav-list');
  await expect(nav.getByRole('link')).toHaveCount(5);
  for (const label of ['总览', '交易记录', 'AI 研究', '通知', '设置']) {
    await expect(nav.getByRole('link', { name: label, exact: true })).toBeVisible();
  }
  await expect(page.locator('.nav-item[aria-current="page"]')).toContainText('总览');

  await nav.getByRole('link', { name: '交易记录', exact: true }).click();
  await expect(page).toHaveURL(/#history\/fills$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('交易记录');
  await expect(page.locator('.nav-item[aria-current="page"]')).toContainText('交易记录');

  // 设置分类支持方向键切换。
  await page.goto(BASE + '/#settings');
  const appearance = page.getByTestId('settings-nav-appearance');
  await expect(appearance).toBeVisible();
  await appearance.click();
  await appearance.press('ArrowDown');
  await expect(page.getByTestId('settings-nav-ai')).toHaveAttribute('aria-selected', 'true');

  // 侧栏底部只保留本机用户信息，不出现内部身份词。
  await expect(page.locator('.sidebar-account')).toContainText('本机用户');
  await expect(page.locator('.sidebar-account')).toContainText('仅本机访问');
  await expect(page.getByText('本机 Owner')).toHaveCount(0);
  await expect(page.getByText('Paper workspace')).toHaveCount(0);
});

test('顶栏系统状态入口与主题持久化', async ({ page }) => {
  await page.goto(BASE + '/#overview');
  const pill = page.locator('.system-pill');
  await expect(pill).toHaveAttribute('href', '#settings/runtime');
  await expect(pill).toHaveAttribute('title', /系统状态/);

  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: '切换到浅色模式' })).toBeVisible();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.goto(BASE + '/#settings');
  const darkChoice = page.locator('[data-theme-choice="dark"]');
  if (await darkChoice.count()) await expect(darkChoice).toHaveAttribute('data-checked', 'true');
  const motion = page.getByRole('switch', { name: '减弱动态效果' });
  await motion.click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'reduce');
  await page.reload();
  await expect(page.getByRole('switch', { name: '减弱动态效果' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('switch', { name: '减弱动态效果' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'full');
});

test('响应式：1280/1440/1920/375 无横向溢出，滚动只发生在一个容器', async ({ page }) => {
  for (const [width, height] of [[1280, 900], [1440, 900], [1920, 1080], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.goto(BASE + '/#overview');
    await expect(page.getByTestId('overview-page')).toBeVisible();
    const layout = await page.evaluate(() => {
      const workspace = document.querySelector('.workspace');
      return {
        overflowX: document.documentElement.scrollWidth - window.innerWidth,
        workspaceOverflowY: workspace ? getComputedStyle(workspace).overflowY : null,
        windowScrollY: window.scrollY,
      };
    });
    expect(layout.overflowX, width + 'px 出现横向溢出').toBeLessThanOrEqual(1);
    expect(['auto', 'scroll'], width + 'px 缺少单滚动容器').toContain(layout.workspaceOverflowY);
    // 主滚动发生在 .workspace 内部：滚动它不会移动 window。
    const scrolled = await page.evaluate(() => {
      const workspace = document.querySelector('.workspace');
      workspace.scrollTop = 240;
      return { windowY: window.scrollY, workspaceY: workspace.scrollTop };
    });
    expect(scrolled.windowY).toBe(0);
    expect(scrolled.workspaceY).toBeGreaterThanOrEqual(0);
  }
});

test('移动端导航：焦点进入抽屉、Escape 关闭并归还焦点', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(BASE + '/#overview');
  const trigger = page.getByRole('button', { name: '打开导航' });
  await trigger.click();
  await expect(page.locator('.overlay--nav')).toBeVisible();
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest('.overlay')))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('.overlay--nav')).toHaveCount(0);
  expect(await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))).toBe('打开导航');
});

test('全局术语巡检：11 个页面主界面禁用词 0、表格对齐、主按钮 ≤1、无 pageerror', async ({ page }) => {
  test.slow();
  const findings = [];
  page.on('pageerror', (error) => findings.push({ kind: 'pageerror', detail: String(error).slice(0, 200) }));
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [hash, title] of PAGES) {
    await page.goto('about:blank');
    await page.goto(BASE + '/' + hash, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(hash === '#agents' ? 2400 : 1200);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    const visible = await mainRegionText(page);
    const result = await page.evaluate(({ banned, enums, text }) => {
      const hits = banned.filter((word) => text.includes(word));
      const lower = text;
      for (const word of enums) {
        const re = new RegExp('(^|[^A-Za-z_])' + word + '([^A-Za-z_]|$)');
        if (re.test(lower)) hits.push('enum:' + word);
      }
      const hashHit = text.match(/[0-9a-f]{32,}/);
      if (hashHit) hits.push('hash:' + hashHit[0].slice(0, 12));
      const primary = document.querySelectorAll('.page-frame .btn--primary').length;
      const tableIssues = [];
      for (const table of document.querySelectorAll('.page-frame .data-table')) {
        for (const cell of table.querySelectorAll('th.num, td.num')) {
          const align = getComputedStyle(cell).textAlign;
          if (align !== 'right') tableIssues.push('num:' + align + ':' + (cell.textContent || '').slice(0, 16));
        }
        for (const cell of table.querySelectorAll('th:not(.num):not([aria-label]), td:not(.num):not(.row-action-cell):not([aria-hidden])')) {
          if ((cell.textContent || '').trim() === '操作') continue;
          const align = getComputedStyle(cell).textAlign;
          if (align !== 'left' && align !== 'start') tableIssues.push('text:' + align + ':' + (cell.textContent || '').slice(0, 16));
        }
      }
      return { hits, primary, tableIssues, overflow: document.documentElement.scrollWidth > window.innerWidth + 1 };
    }, { banned: BANNED, enums: ENUM_WORDS, text: visible });
    if (result.hits.length > 0) findings.push({ kind: 'banned', page: hash, detail: result.hits.join(',') });
    if (result.primary > 1) findings.push({ kind: 'primary-buttons', page: hash, detail: String(result.primary) });
    if (result.tableIssues.length > 0) findings.push({ kind: 'table-align', page: hash, detail: result.tableIssues.slice(0, 5).join(' | ') });
    if (result.overflow) findings.push({ kind: 'overflow', page: hash });
  }
  expect(findings).toEqual([]);
});

test('首次使用协议页：独立页面、只有一个主操作、移动端不溢出', async ({ page }) => {
  await page.goto(AGREEMENT + '/#overview');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('开始之前，只有这一页');
  await expect(page.getByRole('heading', { level: 2 })).toHaveCount(8);
  await expect(page.getByRole('button', { name: '同意并继续' })).toBeVisible();
  await expect(page.locator('.sidebar')).toHaveCount(0);
  await expect(page.locator('.page-frame')).toHaveCount(0);
  await expect(page.getByText('模拟账户')).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});

test('键盘：跳到主要内容、页面标题获得焦点、document.title 随路由更新', async ({ page }) => {
  await page.goto(BASE + '/#overview');
  await expect(page).toHaveTitle(/总览 · Stratide/);
  await page.keyboard.press('Tab');
  const skip = page.locator('.skip-link');
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();

  await page.locator('.sidebar .nav-list').getByRole('link', { name: '通知', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('通知');
  await expect(page).toHaveTitle(/通知 · Stratide/);
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe('H1');
});
