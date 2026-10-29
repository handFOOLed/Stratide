import { test, expect } from '@playwright/test';
import path from 'node:path';

const evidence = path.resolve('../../state/issue20-browser');

test('synthetic account, confirmed fills, rejected orders and all five navigation entries work', async ({ page }) => {
  const errors = []; page.on('pageerror', error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
  await expect(page.locator('.source-line')).toContainText('synthetic_test');
  await expect(page.locator('.source-line')).toContainText('非实时同步');
  await expect(page.locator('.recent-fills tbody tr')).toHaveCount(2);
  await page.getByRole('link',{name:'查看全部 →'}).click();
  await expect(page.locator('.trade-table tbody tr')).toHaveCount(2);
  await page.getByRole('link',{name:'订单状态 (3)'}).click();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(3);
  await expect(page.locator('.orders-table tbody tr').first()).toContainText('已拒绝');
  await expect(page.locator('.orders-table tbody tr').first()).toContainText('0 / 10,000');
  await expect(page.locator('.orders-table .reason').first()).not.toHaveText('');
  await page.getByRole('tab',{name:'账户表现'}).click();
  await expect(page.getByRole('heading',{name:'账户每日记录'})).toBeVisible();
  await page.getByRole('tab',{name:'研究与回测'}).click();
  await expect(page.getByText('尚未配置独立研究结果',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Agent 管理',exact:true}).click();
  await expect(page.getByRole('button',{name:'解锁 Agent 管理'})).toBeVisible();
  await page.getByRole('link',{name:'通知与审批',exact:true}).click();
  await expect(page.getByText('通知服务尚未接入',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'设置',exact:true}).click();
  await expect(page.getByRole('heading',{name:'数据连接'})).toBeVisible();
  await expect(page.getByRole('button',{name:/CSV|PDF|导出/})).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('chart range, metric, sorting, theme and the strategy drawer persist honest state', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  await expect(page.getByRole('button',{name:'30D',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'ALL',exact:true}).click();
  await page.getByRole('button',{name:'累计盈亏',exact:true}).click();
  await page.getByLabel('主题',{exact:true}).selectOption('dark');
  await page.locator('.compact-panel').first().getByRole('button',{name:'名称'}).click();
  await page.getByRole('button',{name:'two-signal-example',exact:true}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('无可信归因指标');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'ALL',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'累计盈亏',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await expect(page.locator('.compact-panel').first().locator('th').first()).toHaveAttribute('aria-sort','descending');
});

test('empty input, broken publication, missing valuation and offline service are visible states', async ({ page }) => {
  await page.goto('http://127.0.0.1:8712');
  await expect(page.getByText('尚未选择 Paper 报告',{exact:true})).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
  await page.goto('http://127.0.0.1:8713');
  await expect(page.getByText('Paper 报告不可用',{exact:true})).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
  await page.goto('http://127.0.0.1:8714');
  await expect(page.getByTestId('nav-value')).toHaveText('—');
  await expect(page.getByRole('status')).toContainText('缺少可信收盘估值');
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  await page.route('**/api/**', route=>route.abort());
  await page.getByRole('button',{name:'↻ 重新连接'}).click();
  await expect(page.getByText('无法连接本地服务',{exact:true})).toBeVisible();
  await expect(page.getByTestId('nav-value')).toHaveCount(0);
});

test('actual synthetic screenshots at 1920, 1366, 1280 and 375 CSS pixels', async ({ page }) => {
  for (const [width,height] of [[1920,1080],[1366,900],[1280,900],[375,812]]) {
    await page.setViewportSize({width,height});
    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toHaveText('¥9,928.93');
    await page.getByLabel('主题',{exact:true}).selectOption('light');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:path.join(evidence,`synthetic-${width}.png`),fullPage:true});
    if (width >= 1366) await page.screenshot({path:path.join(evidence,`synthetic-${width}-viewport.png`)});
  }
});

test('68-day historical report and holding drawer use the explicitly selected frozen account', async ({ page, request }) => {
  test.skip(!process.env.STRATIDE_HISTORICAL_REPORT,'No explicitly selected historical report on this machine');
  const base = 'http://127.0.0.1:8715';
  const account = (await (await request.get(`${base}/api/account`)).json());
  const equity = (await (await request.get(`${base}/api/equity`)).json());
  expect(account.snapshot.mode).toBe('historical_replay');
  expect(equity.data).toHaveLength(68);
  await page.setViewportSize({width:1920,height:1080});
  await page.goto(base);
  await expect(page.getByTestId('nav-value')).toHaveText('¥99,966.51');
  await expect(page.locator('.source-line')).toContainText('historical_replay');
  await page.getByRole('button',{name:'ALL',exact:true}).click();
  await expect(page.locator('.chart-caption')).toContainText('68 个报告日期');
  await page.screenshot({path:path.join(evidence,'historical-1920.png'),fullPage:true});
  await page.screenshot({path:path.join(evidence,'historical-1920-viewport.png')});
  await page.getByRole('button',{name:'600000',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('行情序列不可用');
  await expect(page.getByRole('dialog')).toContainText('100 / 100 股');
  await page.screenshot({path:path.join(evidence,'historical-holding-drawer.png')});
  await page.getByRole('button',{name:'关闭详情'}).click();
  await page.setViewportSize({width:1366,height:900});
  await page.screenshot({path:path.join(evidence,'historical-1366.png'),fullPage:true});
  await page.screenshot({path:path.join(evidence,'historical-1366-viewport.png')});
  if (process.env.STRATIDE_EVALUATION_FILE) {
    await page.goto(`${base}/#history/research`);
    await expect(page.getByRole('heading',{name:'独立研究结果'})).toBeVisible();
    await expect(page.locator('.research-result')).toContainText('不计入账户 NAV');
  }
});
