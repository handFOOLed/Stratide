import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { settle, settleOverlay } from './settle.mjs';

const evidence = path.resolve(process.env.STRATIDE_UI_EVIDENCE_DIR || '../../state/m2-pr03-browser');
mkdirSync(evidence, { recursive: true });

test('overview is the single home for NAV, chart, positions and five recent fills, with no duplicate links', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
  await expect(page.getByText('合成测试').first()).toBeVisible();
  await expect(page.getByText('只读快照', { exact: true })).toBeVisible();
  await expect(page.locator('.recent-fills-card tbody tr')).toHaveCount(2);
  await expect(page.getByText('查看全部', { exact: true })).toHaveCount(0);
  await expect(page.getByText('查看更多', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('img', { name: /当前 Paper 账户资产曲线/ })).toBeVisible();
  await expect(page.getByText('此快照未记录风控锁')).toBeVisible();
  await expect(page.getByRole('heading', { name: '账户资产' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '今日盈亏' })).toBeVisible();
  await expect(page.getByText('交易预留', { exact: true })).toBeVisible();
  await expect(page.locator('.risk-card')).not.toContainText(/累计盈亏|累计收益率|最大日回撤|累计费用/);
  await expect(page.locator('.account-card')).not.toContainText('可用现金');
  await expect(page.locator('.account-card')).not.toContainText('最后估值');
  await expect(page.locator('.recent-fills-card .card__foot')).toContainText('共 2 笔');

  // Type floor: body 15-16px, table and secondary text >= ~13.5px.
  const sizes = await page.evaluate(() => {
    const px = (selector) => {
      const element = document.querySelector(selector);
      return element ? parseFloat(getComputedStyle(element).fontSize) : null;
    };
    return {
      body: px('body'),
      tableCell: px('.data-table td'),
      tableHead: px('.data-table th'),
      subtitle: px('.card__subtitle'),
      summary: px('.account-stat__value'),
    };
  });
  expect(sizes.body).toBeGreaterThanOrEqual(15);
  expect(sizes.tableCell).toBeGreaterThanOrEqual(14);
  expect(sizes.tableHead).toBeGreaterThanOrEqual(13.5);
  expect(sizes.subtitle).toBeGreaterThanOrEqual(13.5);
  expect(sizes.summary).toBeGreaterThanOrEqual(15);

  // An empty position card stays compact, without five fabricated rows.
  const emptyWindow = await page.locator('.positions-card .overview-empty').evaluate((el) => el.getBoundingClientRect().height);
  expect(emptyWindow).toBeLessThan(5 * 44);

  await page.locator('.recent-fills-card tbody tr .row-link').first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('成交金额');
  await expect(dialog).toContainText('佣金');
  await page.getByRole('button', { name: '关闭详情' }).click();
  await expect(dialog).not.toBeVisible();

  await expect(page.locator('.positions-card .empty-state__title')).toHaveText('当前空仓');
  expect(errors).toEqual([]);
});

test('overview P&L uses semantic colors and aligns numbers within each unit group', async ({ page }) => {
  const checkValues = async (tone) => {
    const rendered = await page.evaluate(() => {
      const probe = document.createElement('span');
      document.body.append(probe);
      const colors = { neutral: getComputedStyle(document.body).color };
      for (const name of ['gain', 'loss']) {
        probe.style.color = `var(--${name})`;
        colors[name] = getComputedStyle(probe).color;
      }
      probe.remove();
      const groups = [...document.querySelectorAll('.account-stat-group')].map((group) =>
        [...group.querySelectorAll('.account-stat__value')].map((element) => {
          const parts = [...element.querySelectorAll('[aria-hidden="true"]')];
          return {
            color: getComputedStyle(element).color,
            signX: parts[0].getBoundingClientRect().x,
            currencyX: parts[1].getBoundingClientRect().x,
            decimalX: parts[3].getBoundingClientRect().x,
          };
        }),
      );
      return { colors, groups, daily: getComputedStyle(document.querySelector('.account-delta__value')).color };
    });
    const [amounts, ratios] = rendered.groups;
    expect(amounts[0].color).toBe(rendered.colors[tone]);
    expect(amounts[1].color).toBe(rendered.colors.neutral);
    expect(ratios[0].color).toBe(rendered.colors[tone]);
    expect(ratios[1].color).toBe(rendered.colors.neutral);
    expect(rendered.daily).toBe(rendered.colors[tone]);
    expect(amounts[0].currencyX).toBeLessThan(ratios[0].currencyX);
    expect(Math.abs(amounts[0].currencyX - amounts[1].currencyX)).toBeLessThanOrEqual(0.5);
    for (const values of rendered.groups) {
      expect(Math.abs(values[0].signX - values[1].signX)).toBeLessThanOrEqual(0.5);
      expect(Math.abs(values[0].decimalX - values[1].decimalX)).toBeLessThanOrEqual(0.5);
    }
  };

  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  await checkValues('loss');
  await page.route('**/api{,/v1}/account', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.data.session_pnl_fen = '76';
    body.data.cumulative_pnl_fen = '7107';
    body.data.total_return_bps = '71';
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await expect(page.locator('.account-delta__value')).toHaveText('+¥0.76');
  await checkValues('gain');
});

test('NAV uses its actual range, five equal 20% steps, principal baseline and corresponding short-series points', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  await expect(page.getByRole('button', { name: '30D', exact: true })).toHaveAttribute('aria-pressed', 'true');

  // Actual range and principal, split into five equal display intervals.
  await expect(page.locator('.chart-grid-line')).toHaveCount(6);
  const axis = await page.locator('.chart-svg text').allTextContents();
  expect(axis).toContain('本金');
  expect(axis).not.toContain('¥0');
  const dash = await page.locator('.chart-grid-line').first().evaluate((el) => getComputedStyle(el).strokeDasharray);
  expect(dash).not.toBe('none');

  // Short series retain a point for each actual observation.
  const standing = await page.locator('.chart-svg circle').count();
  expect(standing).toBeGreaterThan(0);
  await page.locator('.chart-svg').hover({ position: { x: 220, y: 90 } });
  await expect(page.locator('.chart-svg circle')).toHaveCount(standing + 1);
  await page.mouse.move(2, 2);
  await expect(page.locator('.chart-svg circle')).toHaveCount(standing);

  await page.getByRole('button', { name: '全部', exact: true }).click();
  await expect(page.locator('.chart-card .card__subtitle')).toContainText('4 个报告日');
  await expect(page.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await expect(page.getByRole('group', { name: '图表指标' })).toHaveCount(0);

  await page.getByRole('button', { name: '切换到深色主题' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('group', { name: '图表指标' })).toHaveCount(0);

  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('history tabs hold the complete records, daily reconciliation and independent research without duplicating the overview chart', async ({ page }) => {
  await page.goto('/#history/fills');
  await expect(page.locator('.fills-table tbody tr')).toHaveCount(2);
  await page.locator('.fills-table tbody tr .row-link').first().click();
  const fillDialog = page.getByRole('dialog');
  await expect(fillDialog).toContainText('成交金额');
  await expect(fillDialog).toContainText('关联订单');
  await expect(fillDialog.locator('.fee-table:not(.fee-table--plain) dt')).toHaveText(['佣金', '印花税', '过户费']);
  await expect(fillDialog.locator('.fill-summary__fee')).toHaveText('¥0.76');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();

  await page.getByRole('tab', { name: /订单/ }).click();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(3);
  await expect(page.locator('.orders-table tbody tr').first()).toContainText('已拒绝');
  await page.locator('.orders-table tbody tr .row-link').first().click();
  const orderDialog = page.getByRole('dialog');
  await expect(orderDialog).toContainText('原始原因');
  // The server reason is shown verbatim, not rewritten by the front end.
  await expect(orderDialog.locator('.prose')).toContainText('可用资金不足');
  await expect(orderDialog).toContainText('此订单没有已确认的模拟成交');
  await page.getByRole('button', { name: '关闭详情' }).click();

  await page.getByRole('tab', { name: '逐日核对' }).click();
  await expect(page.locator('.daily-table tbody tr')).toHaveCount(4);
  await expect(page.getByRole('tabpanel', { name: '逐日核对' })).toBeVisible();
  await expect(page.locator('.chart-svg')).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: '隐含持仓' })).toBeVisible();
  await page.locator('.daily-table tbody tr .row-link').first().click();
  await expect(page.getByRole('dialog')).toContainText('隐含持仓市值');
  await page.getByRole('button', { name: '关闭详情' }).click();

  await page.getByRole('tab', { name: /策略档案/ }).click();
  await expect(page.getByText('two-signal-example').first()).toBeVisible();
  await page.locator('.data-table tbody tr .row-link').first().click();
  await expect(page.getByRole('dialog')).toContainText('不可用');
  await page.getByRole('button', { name: '关闭详情' }).click();

  await page.getByRole('tab', { name: /研究档案/ }).click();
  await expect(page.getByText('尚未配置独立研究结果', { exact: true })).toBeVisible();
});

test('notifications are honest and settings show one category at a time with working appearance controls', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/#notifications');
  await expect(page.getByRole('heading', { name: '通知审批' })).toBeVisible();
  await expect(page.getByText('本机研究控制尚未解锁。', {exact:true})).toBeVisible();
  await expect(page.getByRole('button', {name:'前往 Agent 管理解锁'})).toBeVisible();
  await expect(page.locator('[data-testid="nav-value"]')).toHaveCount(0);

  await page.goto('/#settings');
  await expect(page.getByRole('tab', { name: '外观' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel', { name: '外观' })).toBeVisible();
  await page.locator('[data-theme-choice="dark"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('[data-theme-choice="light"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  const motionSwitch = page.getByRole('switch', { name: '减弱动态效果' });
  await expect(motionSwitch).toHaveAttribute('aria-checked', 'false');
  await motionSwitch.click();
  await expect(motionSwitch).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'reduce');
  await page.reload();
  await expect(motionSwitch).toHaveAttribute('aria-checked', 'true');
  await motionSwitch.click();
  await expect(motionSwitch).toHaveAttribute('aria-checked', 'false');
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'full');

  // One category at a time: selecting data removes the appearance controls.
  await page.getByRole('tab', { name: '数据连接' }).click();
  await expect(page.getByRole('tabpanel', { name: '数据连接' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '数据连接' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-theme-choice="dark"]')).toHaveCount(0);
  await expect(page.locator('.data-card')).toContainText('snapshot_id');

  await page.getByRole('tab', { name: '权限与安全' }).click();
  await expect(page.getByRole('tabpanel', { name: '权限与安全' })).toBeVisible();
  await expect(page.getByText('Paper 模式', { exact: true })).toBeVisible();
  await expect(page.getByText('Owner 令牌仅内存', { exact: true })).toBeVisible();

  // Keyboard navigation keeps the settings categories reachable.
  await page.getByRole('tab', { name: '权限与安全' }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('tab', { name: '关于' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel', { name: '关于' })).toBeVisible();
});

test('empty, invalid, missing-valuation and offline states stay visible and honest', async ({ page }) => {
  await page.goto('http://127.0.0.1:8732/');
  await expect(page.getByText('当前 Paper 账户尚未配置', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  await page.goto('http://127.0.0.1:8733/');
  await expect(page.getByText('Paper 报告不可用', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('http://127.0.0.1:8734/');
  await settle(page, '.page-frame');
  await page.screenshot({ path: path.join(evidence, 'overview-missing-nav-1366-light.png'), animations: 'disabled' });
  await expect(page.getByTestId('nav-value')).toHaveText('—');
  await expect(page.getByText('最后估值缺失', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('缺少可信收盘估值').first()).toBeVisible();
  await expect(page.locator('.chart-card .card__subtitle')).toContainText('缺 1 日');

  await page.goto('/');
  await page.route('**/api/**', (route) => route.abort());
  await page.reload();
  await expect(page.getByText('无法连接本地服务', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
});

test('re-sorting rows never animates cell borders or paints a dark hairline', async ({ page }) => {
  await page.goto('/#history/fills');
  await expect(page.locator('.fills-table tbody tr')).toHaveCount(2);

  const collapse = await page.locator('.fills-table').evaluate((el) => getComputedStyle(el).borderCollapse);
  expect(collapse).toBe('separate');

  const readCell = () =>
    page.locator('.fills-table tbody td').first().evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        transition: style.transitionProperty,
        borderColor: style.borderBottomColor,
        borderWidth: style.borderBottomWidth,
      };
    });

  const before = await readCell();
  expect(before.transition).not.toContain('border-color');
  expect(before.borderWidth).toBe('1px');

  const order = () => page.locator('.fills-table tbody tr .row-link').allTextContents();
  const first = await order();
  await page.getByRole('button', { name: '最早优先', exact: true }).click();
  await expect.poll(order).toEqual([...first].reverse());
  await page.getByRole('button', { name: '最新优先', exact: true }).click();
  await expect.poll(order).toEqual(first);

  const after = await readCell();
  expect(after.borderColor).toBe(before.borderColor);
  expect(after.transition).toBe(before.transition);
  const running = await page.locator('.fills-table tbody tr').first().evaluate((el) => el.getAnimations().length);
  expect(running).toBe(0);
});

test('real browser screenshots at 1920, 1366 and 375 for light, dark, drawer and modal', async ({ page }) => {
  for (const [width, height] of [[1920, 1080], [1366, 768], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
    const isDark = (await page.locator('html').getAttribute('data-theme')) === 'dark';
    if (isDark) await page.getByRole('button', { name: '切换到浅色主题' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await settle(page, '.page-frame');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(evidence, 'overview-' + width + '-light.png'), animations: 'disabled' });
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await settle(page, '.page-frame');
    await page.screenshot({ path: path.join(evidence, 'overview-' + width + '-dark.png'), animations: 'disabled' });
    if (width === 1366) {
      await page.goto('/#history/fills');
      await settle(page, '.page-frame');
      await page.screenshot({ path: path.join(evidence, 'history-1366-dark.png'), animations: 'disabled' });
      await page.getByRole('button', { name: '切换到浅色主题' }).click();
      await page.locator('.fills-table tbody tr .row-link').first().click();
      await settleOverlay(page);
      await expect(page.locator('.drawer')).toContainText('成交金额');
      await page.screenshot({ path: path.join(evidence, 'fill-drawer-1366-light.png'), animations: 'disabled' });
      await page.getByRole('button', { name: '关闭详情' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
    }
  }

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/#settings');
  await settle(page, '.page-frame');
  await page.getByRole('button', { name: '切换到浅色主题' }).click();
  await page.screenshot({ path: path.join(evidence, 'settings-1366-light.png'), animations: 'disabled' });
  await page.getByRole('button', { name: '切换到深色主题' }).click();
  await settle(page, '.page-frame');
  await page.screenshot({ path: path.join(evidence, 'settings-1366-dark.png'), animations: 'disabled' });
  await page.getByRole('tab', { name: '数据连接' }).click();
  await expect(page.getByRole('tabpanel', { name: '数据连接' })).toBeVisible();
  await page.screenshot({ path: path.join(evidence, 'settings-data-1366-dark.png'), animations: 'disabled' });
  await page.getByRole('button', { name: '切换到浅色主题' }).click();

  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  const accountTrigger = page.getByRole('button', { name: /本机 Owner/ });
  await accountTrigger.click();
  await settle(page, '.account-menu');
  await page.screenshot({ path: path.join(evidence, 'profile-menu-1366-light.png'), animations: 'disabled' });
  await page.keyboard.press('Escape');

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/#settings');
  await settle(page, '.page-frame');
  await page.screenshot({ path: path.join(evidence, 'settings-375-light.png'), animations: 'disabled' });

  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/#agents');
  await settle(page, '.page-frame');
  await page.screenshot({ path: path.join(evidence, 'agent-locked-1366-dark.png'), animations: 'disabled' });
  await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
  await settleOverlay(page);
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.screenshot({ path: path.join(evidence, 'agent-unlock-modal-1366-dark.png'), animations: 'disabled' });
  await page.getByRole('button', { name: '关闭对话框' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
  await settleOverlay(page);
  const modal = page.locator('.modal');
  await expect(modal).toBeVisible();
  const box = await modal.boundingBox();
  expect(box).not.toBeNull();
  if (box) {
    expect(box.width).toBeLessThanOrEqual(375);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(812);
  }
  await page.screenshot({ path: path.join(evidence, 'agent-unlock-modal-375-dark.png'), animations: 'disabled' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
