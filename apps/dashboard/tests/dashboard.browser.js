import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const evidence = path.resolve('../../state/m2-pr03-browser');
mkdirSync(evidence, { recursive: true });

test('overview is the single home for NAV, chart, positions and five recent fills, with no duplicate links', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
  await expect(page.getByText('合成测试').first()).toBeVisible();
  await expect(page.getByText('不是实时行情')).toBeVisible();
  await expect(page.locator('.recent-fills-card tbody tr')).toHaveCount(2);
  await expect(page.getByText('查看全部', { exact: true })).toHaveCount(0);
  await expect(page.getByText('查看更多', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('img', { name: /当前 Paper 账户资产曲线/ })).toBeVisible();

  await page.locator('.recent-fills-card tbody tr .row-link').first().click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('模拟记账时间');
  await expect(dialog).toContainText('佣金');
  await page.getByRole('button', { name: '关闭详情' }).click();
  await expect(dialog).not.toBeVisible();

  await expect(page.locator('.positions-card .empty-state__title')).toHaveText('当前空仓');
  expect(errors).toEqual([]);
});

test('chart ranges, metrics and theme persist without hiding missing data', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  await expect(page.getByRole('button', { name: '30D', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: '全部', exact: true }).click();
  await page.getByRole('button', { name: '累计盈亏', exact: true }).click();
  await expect(page.locator('.chart-caption')).toContainText('4 个报告日');
  await expect(page.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: '切换到深色主题' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: '累计盈亏', exact: true })).toHaveAttribute('aria-pressed', 'true');

  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('history tabs hold the complete records, daily reconciliation and independent research without duplicating the overview chart', async ({ page }) => {
  await page.goto('/#history/fills');
  await expect(page.locator('.fills-table tbody tr')).toHaveCount(2);
  await page.locator('.fills-table tbody tr .row-link').first().click();
  await expect(page.getByRole('dialog')).toContainText('费用拆分');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();

  await page.getByRole('tab', { name: /订单/ }).click();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(3);
  await expect(page.locator('.orders-table tbody tr').first()).toContainText('已拒绝');
  await page.locator('.orders-table tbody tr .row-link').first().click();
  await expect(page.getByRole('dialog')).toContainText('委托意图不等于实际成交');
  await page.getByRole('button', { name: '关闭详情' }).click();

  await page.getByRole('tab', { name: '逐日核对' }).click();
  await expect(page.locator('.daily-table tbody tr')).toHaveCount(4);
  await expect(page.getByRole('heading', { name: '逐日核对' })).toBeVisible();
  await expect(page.locator('.chart-svg')).toHaveCount(0);
  await expect(page.getByText('隐含持仓')).toBeVisible();
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

test('notifications and settings are honest, non-duplicating states with working appearance controls', async ({ page }) => {
  await page.goto('/#notifications');
  await expect(page.getByRole('heading', { name: '通知与审批' })).toBeVisible();
  await expect(page.getByText('通知渠道', { exact: true })).toBeVisible();
  await expect(page.getByText('审批', { exact: true })).toBeVisible();
  await expect(page.getByText('未接入').first()).toBeVisible();
  await expect(page.locator('[data-testid="nav-value"]')).toHaveCount(0);

  await page.goto('/#settings');
  await expect(page.getByRole('heading', { name: '数据连接' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '本机权限边界' })).toBeVisible();
  await page.locator('.theme-choice').filter({ hasText: '深色' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('.theme-choice').filter({ hasText: '浅色' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.getByRole('button', { name: '减少动效' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'reduce');
  await page.getByRole('button', { name: '跟随系统' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'full');
});

test('empty, invalid, missing-valuation and offline states stay visible and honest', async ({ page }) => {
  await page.goto('http://127.0.0.1:8732/');
  await expect(page.getByText('尚未选择 Paper 报告', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  await page.goto('http://127.0.0.1:8733/');
  await expect(page.getByText('Paper 报告不可用', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  await page.goto('http://127.0.0.1:8734/');
  await expect(page.getByTestId('nav-value')).toHaveText('—');
  await expect(page.getByText('最后估值缺失', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('缺少可信收盘估值').first()).toBeVisible();
  await expect(page.locator('.chart-caption')).toContainText('缺估值 1 日');

  await page.goto('/');
  await page.route('**/api/**', (route) => route.abort());
  await page.reload();
  await expect(page.getByText('无法连接本地服务', { exact: true })).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
});

test('real browser screenshots at 1920, 1366 and 375 for light, dark, drawer and modal', async ({ page }) => {
  for (const [width, height] of [[1920, 1080], [1366, 768], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
    const isDark = (await page.locator('html').getAttribute('data-theme')) === 'dark';
    if (isDark) await page.getByRole('button', { name: '切换到浅色主题' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(evidence, 'overview-' + width + '-light.png') });
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await page.screenshot({ path: path.join(evidence, 'overview-' + width + '-dark.png') });
    if (width === 1366) {
      await page.goto('/#history/fills');
      await page.screenshot({ path: path.join(evidence, 'history-1366-dark.png') });
      await page.getByRole('button', { name: '切换到浅色主题' }).click();
      await page.locator('.fills-table tbody tr .row-link').first().click();
      await page.screenshot({ path: path.join(evidence, 'fill-drawer-1366-light.png') });
      await page.getByRole('button', { name: '关闭详情' }).click();
    }
  }

  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/#agents');
  await page.screenshot({ path: path.join(evidence, 'agent-locked-1366-dark.png') });
  await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.screenshot({ path: path.join(evidence, 'agent-unlock-modal-1366-dark.png') });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: path.join(evidence, 'agent-unlock-modal-375-dark.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});