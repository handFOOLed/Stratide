import { test, expect } from '@playwright/test';
import { settleOverlay } from './settle.mjs';

/**
 * 交易记录 / 总览 / 设置 的浏览器回归（当前 UI）。
 * fixture 场景：8731 synthetic（正常态），8732 empty，8733 invalid，8734 missing-nav。
 */
const SYNTHETIC = 'http://127.0.0.1:8731';
const EMPTY = 'http://127.0.0.1:8732';
const INVALID = 'http://127.0.0.1:8733';
const MISSING_NAV = 'http://127.0.0.1:8734';

async function openDialog(page) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe.configure({ mode: 'serial' });

test('总览：健康条、总资产、交易保护与空持仓/成交如实显示', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(SYNTHETIC + '/#overview');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('总览');
  await expect(page.getByTestId('overview-page')).toBeVisible();

  // 顶部健康条：四项都来自真实接口，不是写死文案。
  const health = page.getByRole('list', { name: '账户与系统状态' });
  await expect(health).toBeVisible();
  for (const label of ['模拟账户', '数据更新至', '系统状态', 'AI 研究']) {
    await expect(health).toContainText(label);
  }
  await expect(page.getByTestId('overview-data-date')).toHaveText('数据日期 2026-11-02');
  await expect(page.getByTestId('overview-updated-at')).toContainText(/更新于 \d{4}-\d{2}-\d{2} \d{2}:\d{2}/);

  // 第一屏资产与交易保护。
  await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
  await expect(page.getByTestId('session-pnl')).toContainText('−¥0.76');
  await expect(page.getByTestId('cumulative-pnl')).toContainText('−¥71.07');
  await expect(page.getByTestId('protection-normal')).toContainText('交易保护正常');
  await expect(page.getByRole('heading', { name: /总资产/ })).toBeVisible();

  // 核心概念说明（?）按钮可访问。
  for (const label of ['数据日期说明', '总资产说明', '交易保护说明']) {
    await expect(page.getByRole('button', { name: label })).toHaveCount(1);
  }

  // 上手清单来自真实状态：1 / 5，且逐项状态可见。
  await expect(page.locator('.checklist__progress')).toHaveText('1 项 / 5 项');
  await expect(page.locator('.checklist__items')).toContainText('设置 AI 研究');

  // 资产曲线与区间切换。
  await expect(page.getByTestId('equity-chart')).toBeVisible();
  await page.getByRole('button', { name: '全部', exact: true }).click();
  await expect(page.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');

  // 空持仓 / 成交保持紧凑，不伪造行。
  await expect(page.getByTestId('positions-card')).toContainText('当前空仓');
  await expect(page.getByTestId('fills-card')).toContainText('最近成交');
  await expect(page.locator('[data-testid="fill-row"]')).toHaveCount(2);
  await expect(page.getByText('查看全部', { exact: true })).toHaveCount(0);

  // 诊断信息默认收起，展开后保留原始字段。
  const diagnostics = page.getByTestId('overview-diagnostics').locator('details.diagnostics');
  await expect(diagnostics).toHaveJSProperty('open', false);
  await diagnostics.locator('summary').click();
  await expect(diagnostics).toHaveJSProperty('open', true);
  await expect(diagnostics).toContainText('快照标识');

  expect(errors).toEqual([]);
});

test('总览：账户接口失败时显示错误态而不是旧数据', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.abort());
  await page.route('**/api/current/**', (route) => route.abort());
  await page.goto(SYNTHETIC + '/#overview');
  await expect(page.getByText(/无法连接本地服务|读取失败/).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
});

test('交易记录·成交：三 Tab、抽屉焦点、高级记录与诊断折叠', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#history/fills');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('交易记录');
  await expect(page.getByRole('tab')).toHaveCount(3);
  for (const name of [/^成交/, /^订单/, /^每日账本/]) {
    await expect(page.getByRole('tab', { name })).toBeVisible();
  }
  await expect(page.getByTestId('history-data-date')).toContainText('数据日期 2026-11-02');

  // 成交表与详情抽屉。
  await expect(page.locator('[data-testid="fill-row"]')).toHaveCount(2);
  await page.locator('[data-testid="fill-row"] .row-link').first().click();
  const dialog = await openDialog(page);
  await settleOverlay(page);
  await expect(dialog.locator('[data-testid="fill-drawer"]')).toBeVisible();
  await expect(dialog).toContainText('成交金额');
  await expect(dialog).toContainText('佣金');
  await expect(dialog).toContainText('时间与记录');
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => Boolean(document.activeElement?.closest('[data-testid="fill-row"]')))).toBe(true);

  // 旧 Tab（策略档案/研究档案）不再出现；高级记录只作留档。
  await expect(page.getByRole('tab', { name: /策略档案|研究档案/ })).toHaveCount(0);
  const advanced = page.getByTestId('advanced-records');
  await expect(advanced).toHaveJSProperty('open', false);
  await page.getByTestId('advanced-records-toggle').click();
  await expect(advanced).toHaveJSProperty('open', true);
  await expect(advanced).toContainText('策略版本记录');
  await expect(advanced).toContainText('数据与快照');
  await expect(page.locator('[data-testid="strategy-row"]')).not.toHaveCount(0);
  const innerDiagnostics = advanced.locator('details.diagnostics');
  await expect(innerDiagnostics.first()).toHaveJSProperty('open', false);
});

test('交易记录·订单：原因人话显示，未知枚举不进入主界面', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#history/orders');
  await expect(page.locator('[data-testid="order-row"]')).toHaveCount(3);
  const rejected = page.locator('[data-testid="order-row"]').filter({ hasText: '已拒绝' }).first();
  await expect(rejected).toBeVisible();
  await expect(rejected).toContainText('可用资金不足');
  await expect(page.getByText('原始原因', { exact: true })).toHaveCount(0);

  // 主界面（诊断折叠区之外）不出现原始枚举/方向英文。
  const mainText = await page.evaluate(() => {
    const parts = [];
    const walk = (node) => {
      if (node.nodeType === Node.TEXT_NODE) { parts.push(node.textContent || ''); return; }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const el = node;
      if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return;
      if (el.matches('details.diagnostics')) return;
      for (const child of el.childNodes) walk(child);
    };
    walk(document.querySelector('.page-frame') || document.body);
    return parts.join(' ');
  });
  for (const word of ['Rejected', 'PartiallyFilled', 'Filled', 'Expired', 'Buy', 'Sell']) {
    expect(mainText).not.toContain(word);
  }

  await page.locator('[data-testid="order-row"]').first().click();
  const dialog = await openDialog(page);
  await settleOverlay(page);
  await expect(dialog.locator('[data-testid="order-drawer"]')).toBeVisible();
  await expect(dialog).toContainText('原因');
  await expect(dialog).toContainText('关联成交');
  await page.getByRole('button', { name: '关闭详情' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('交易记录·每日账本：摘要与列名使用新术语，抽屉显示数据正常', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#history/daily');
  await expect(page.getByTestId('daily-table')).toBeVisible();
  await expect(page.locator('[data-testid="daily-row"]')).toHaveCount(4);
  const summary = page.locator('.history-summary').first();
  await expect(summary).toContainText('报告区间');
  await expect(summary).toContainText('交易日数');
  await expect(summary).toContainText('初始资金');
  await expect(summary).toContainText('资金转入转出');
  await expect(page.getByRole('columnheader', { name: '持仓市值' })).toBeVisible();
  await expect(page.getByText('隐含持仓', { exact: true })).toHaveCount(0);

  await page.locator('[data-testid="daily-row"]').first().click();
  const dialog = await openDialog(page);
  await settleOverlay(page);
  await expect(dialog.locator('[data-testid="day-drawer"]')).toBeVisible();
  await expect(dialog).toContainText('数据正常');
  await expect(dialog).toContainText('较上一数据日');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('通知：空状态、全部标为已读禁用、通知诊断区正确', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#notifications');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('通知');
  await expect(page.locator('.empty-state__title')).toHaveText('还没有通知');
  const markAll = page.getByRole('button', { name: /标记本页已读|全部标为已读/ });
  await expect(markAll).toBeDisabled();
  const diagnostics = page.locator('details.diagnostics').last();
  await diagnostics.locator('summary').click();
  await expect(diagnostics).toContainText('本页通知条数');
  await expect(diagnostics).toContainText('本页未读条数');
  await expect(diagnostics).toContainText('全部未读条数');
});

test('设置·数据与行情 / 关于：人话优先，技术字段只在诊断折叠区', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#settings/data');
  await expect(page.getByTestId('settings-nav-data')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('data-section')).toBeVisible();
  await expect(page.getByTestId('data-facts')).toContainText('Tushare');
  await expect(page.getByTestId('data-facts')).toContainText('不是实时行情');
  await expect(page.getByTestId('data-integrity-status')).toContainText('数据正常');
  await expect(page.getByTestId('data-date')).toContainText('数据日期 2026-11-02');
  const quality = page.getByTestId('data-quality-details').locator('details.diagnostics').first();
  await expect(quality).toHaveJSProperty('open', false);
  await quality.locator('summary').click();
  await expect(quality).toContainText('账户快照');
  await expect(page.getByText('snapshot_id', { exact: true })).toHaveCount(0);

  await page.goto(SYNTHETIC + '/#settings/about');
  await expect(page.getByTestId('about-version')).toContainText('版本');
  await expect(page.getByTestId('feedback-link')).toHaveAttribute('href', /github\.com/);
  await expect(page.getByText(/React|esbuild|N100|scripts\/local-backup/)).toHaveCount(0);
});

test('设置·系统与诊断：整体状态、7 项依赖与折叠区', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#settings/runtime');
  await expect(page.getByTestId('overall-status')).toBeVisible();
  await expect(page.locator('[data-testid="dependency-row"]')).toHaveCount(7);
  await expect(page.getByTestId('dependency-list')).toContainText('行情自动采集');
  await expect(page.getByTestId('dependency-list')).toContainText('AI 研究服务');
  await expect(page.locator('[data-testid="dependency-row"][data-state]')).not.toHaveCount(0);
  await expect(page.getByTestId('version')).toContainText('版本');
  await expect(page.getByTestId('check-update')).toBeVisible();
  const logs = page.getByTestId('recent-logs');
  await expect(logs).toHaveJSProperty('open', false);
  const engine = page.getByTestId('local-engine-settings');
  await expect(engine).toHaveJSProperty('open', false);
  await expect(page.getByTestId('backfill-start').or(page.getByTestId('backfill-restart'))).toBeVisible();
});

test('设置·AI 服务与预算：预算与数据源、错误提示如实', async ({ page }) => {
  await page.goto(SYNTHETIC + '/#settings/ai');
  await expect(page.getByTestId('provider-panel')).toBeVisible();
  await expect(page.getByTestId('provider-panel')).toContainText('¥5.00 / 日');
  await expect(page.getByTestId('provider-panel')).toContainText('¥100.00 / 月');
  await expect(page.getByTestId('provider-key')).toBeVisible();
  await expect(page.getByTestId('provider-save')).toBeDisabled();
});

test('空态 / 无效数据 / 缺失估值：三种数据状态都有诚实提示', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.goto(EMPTY + '/#overview');
  await expect(page.getByText('尚未配置模拟账户', { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  await page.goto(MISSING_NAV + '/#overview');
  await expect(page.getByTestId('nav-value')).toHaveText('—');
  await expect(page.getByTestId('overview-as-of')).toContainText('最后有效估值日');
  await expect(page.getByTestId('protection-alert')).toBeVisible();
  await expect(page.getByText('数据缺失，暂无法可靠估值', { exact: false })).toBeVisible();

  await page.goto(INVALID + '/#overview');
  await expect(page.getByText('模拟账户数据不可用', { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);

  expect(errors).toEqual([]);
});
