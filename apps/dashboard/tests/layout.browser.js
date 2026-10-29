import { test, expect } from '@playwright/test';
import { settle, settleOverlay } from './settle.mjs';

async function measure(page) {
  return page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector);
      return element ? element.getBoundingClientRect() : null;
    };
    const workspace = document.querySelector('.workspace');
    const title = rect('.page-title');
    const card = rect('.main-inner .card');
    const breadcrumb = rect('.breadcrumb');
    const tabs = rect('.tabs-bar');
    const inner = rect('.main-inner');
    return {
      titleX: title ? title.x : null,
      cardX: card ? card.x : null,
      breadcrumbX: breadcrumb ? breadcrumb.x : null,
      tabsX: tabs ? tabs.x : null,
      innerX: inner ? inner.x : null,
      innerWidth: inner ? inner.width : null,
      workspaceClientWidth: workspace ? workspace.clientWidth : null,
      workspaceClientHeight: workspace ? workspace.clientHeight : null,
      workspaceScrollHeight: workspace ? workspace.scrollHeight : null,
      scrollbarGutter: workspace ? getComputedStyle(workspace).scrollbarGutter : null,
      bodyOverflow: getComputedStyle(document.body).overflow,
      docScrollWidth: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    };
  });
}

function closeTo(a, b, label = '', tolerance = 0.75) {
  const message = (label ? label + ': ' : '') + String(a) + ' vs ' + String(b);
  expect(a, message).not.toBeNull();
  expect(b, message).not.toBeNull();
  expect(Math.abs((a ?? 0) - (b ?? 0)), message).toBeLessThanOrEqual(tolerance);
}

test('single scroll container, stable gutter and aligned left edges across pages, themes and overlays', async ({ page }) => {
  for (const [width, height] of [[1920, 1080], [1366, 768], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toBeVisible();
    const overview = await measure(page);

    await page.goto('/#history/fills');
    await expect(page.locator('.fills-table tbody tr')).toHaveCount(2);
    const history = await measure(page);

    await page.goto('/#agents');
    await expect(page.getByText('解锁本机研究控制').first()).toBeVisible();
    const agents = await measure(page);

    await page.goto('/#settings');
    await expect(page.getByRole('heading', { name: '外观' })).toBeVisible();
    const settings = await measure(page);

    for (const state of [overview, history, agents, settings]) {
      expect(state.scrollbarGutter).toBe('stable');
      expect(state.bodyOverflow).toBe('hidden');
      expect(state.docScrollWidth).toBeLessThanOrEqual(state.viewport);
    }

    // Content starts on the same left baseline as the page title. Settings puts
    // its category rail first, so the rail (not the first card) carries the edge.
    closeTo(overview.titleX, overview.cardX, 'overview title/card @' + width);
    closeTo(history.titleX, history.cardX, 'history title/card @' + width);
    closeTo(agents.titleX, agents.cardX, 'agents title/card @' + width);
    closeTo(settings.titleX, await page.locator('.settings-nav').evaluate((el) => el.getBoundingClientRect().x), 'settings title/rail @' + width);

    closeTo(overview.innerX, history.innerX);
    closeTo(history.innerX, agents.innerX);
    closeTo(agents.innerX, settings.innerX);
    closeTo(overview.innerWidth, history.innerWidth);
    closeTo(history.innerWidth, agents.innerWidth);
    if (width >= 960) {
      closeTo(overview.breadcrumbX, overview.titleX);
      closeTo(history.breadcrumbX, history.titleX);
      closeTo(agents.breadcrumbX, agents.titleX);
      closeTo(settings.breadcrumbX, settings.titleX);
      closeTo(history.tabsX, history.titleX);
    }

    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toBeVisible();
    const beforeDrawer = await measure(page);
    await page.locator('.recent-fills-card tbody tr .row-link').first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    const withDrawer = await measure(page);
    closeTo(beforeDrawer.titleX, withDrawer.titleX);
    closeTo(beforeDrawer.cardX, withDrawer.cardX);
    closeTo(beforeDrawer.workspaceClientWidth, withDrawer.workspaceClientWidth);
    await page.getByRole('button', { name: '关闭详情' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    await page.goto('/#agents');
    await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    const withModal = await measure(page);
    closeTo(agents.titleX, withModal.titleX);
    closeTo(agents.cardX, withModal.cardX);
    closeTo(agents.workspaceClientWidth, withModal.workspaceClientWidth);
    await page.getByRole('button', { name: '关闭对话框' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    const beforeTheme = await measure(page);
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const withTheme = await measure(page);
    closeTo(beforeTheme.titleX, withTheme.titleX);
    closeTo(beforeTheme.cardX, withTheme.cardX);
    closeTo(beforeTheme.workspaceClientWidth, withTheme.workspaceClientWidth);
    await page.getByRole('button', { name: '切换到浅色主题' }).click();
  }
});

test('overview fits one desktop screen at 1920x1080 and 1366x768', async ({ page }) => {
  for (const [width, height] of [[1920, 1080], [1366, 768]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');
    await expect(page.getByTestId('nav-value')).toBeVisible();
    const state = await measure(page);
    expect(state.workspaceScrollHeight).toBeLessThanOrEqual(state.workspaceClientHeight + 1);
    const account = await page.locator('.account-card').boundingBox();
    const chart = await page.locator('.chart-card').boundingBox();
    const positions = await page.locator('.positions-card').boundingBox();
    const fills = await page.locator('.recent-fills-card').boundingBox();
    expect(account && chart && positions && fills).toBeTruthy();
    if (account && chart && positions && fills) {
      // Same row = same top edge; allow sub-pixel rounding from fractional grid tracks.
      expect(chart.x).toBeGreaterThan(account.x + account.width - 1);
      expect(Math.abs(chart.y - account.y)).toBeLessThanOrEqual(2);
      expect(positions.y).toBeGreaterThan(account.y + account.height - 1);
      expect(fills.x).toBeGreaterThan(positions.x + positions.width - 1);
      expect(Math.abs(fills.y - positions.y)).toBeLessThanOrEqual(2);
      expect(positions.height).toBeGreaterThanOrEqual(5 * 44);
    }
  }
});

test('a page that outgrows the viewport keeps the content baseline and gutter stable', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  const short = await measure(page);
  expect(short.workspaceScrollHeight).toBeLessThanOrEqual(short.workspaceClientHeight + 1);

  await page.evaluate(() => {
    const spacer = document.createElement('div');
    spacer.id = 'layout-test-spacer';
    spacer.style.height = '1600px';
    document.querySelector('.main-inner')?.appendChild(spacer);
  });
  const long = await measure(page);
  expect(long.workspaceScrollHeight).toBeGreaterThan(long.workspaceClientHeight);
  closeTo(short.innerX, long.innerX);
  closeTo(short.innerWidth, long.innerWidth);
  closeTo(short.titleX, long.titleX);
  closeTo(short.cardX, long.cardX);
  expect(long.docScrollWidth).toBeLessThanOrEqual(long.viewport);
  await page.evaluate(() => document.getElementById('layout-test-spacer')?.remove());
});

test('positions keep a five-row window and paginate beyond it', async ({ page }) => {
  const codes = ['600519', '600036', '601318', '000001', '000002', '300750', '600000'];
  await page.route('**/api/positions', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.data = codes.map((code, index) => ({
      instrument: { code, market: index % 2 === 0 ? 'Shanghai' : 'Shenzhen' },
      quantity: String(100 * (index + 1)),
      sellable_shares: String(100 * (index + 1)),
      unsettled_shares: '0',
      reserved_sell_shares: '0',
      market_value_fen: String(100000 + index * 1000),
      cost_basis_fen: '100000',
      unrealized_pnl_fen: String(index * 500 - 1000),
      lots: [],
      deployment: { deployment_id: 'd', frozen_version: 'v', group_id: 'g', strategy_id: 's' },
    }));
    await route.fulfill({ response, json: body });
  });

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/');
  await expect(page.locator('.positions-card tbody tr')).toHaveCount(5);
  const pager = page.getByRole('group', { name: '持仓分页' });
  await expect(pager).toBeVisible();
  await expect(page.locator('.positions-card .card__foot')).toContainText('1–5 / 共 7 条');
  const firstPageCodes = await page.locator('.positions-card tbody tr td:first-child').allTextContents();
  expect(firstPageCodes).toEqual(['000001', '000002', '300750', '600000', '600036']);
  const heightPage1 = (await page.locator('.positions-card').boundingBox())?.height ?? 0;

  await pager.getByRole('button', { name: '下一页' }).click();
  await expect(page.locator('.positions-card tbody tr')).toHaveCount(2);
  await expect(page.locator('.positions-card .card__foot')).toContainText('6–7 / 共 7 条');
  const secondPageCodes = await page.locator('.positions-card tbody tr td:first-child').allTextContents();
  expect(secondPageCodes).toEqual(['600519', '601318']);
  const heightPage2 = (await page.locator('.positions-card').boundingBox())?.height ?? 0;
  expect(Math.abs(heightPage1 - heightPage2)).toBeLessThanOrEqual(1);

  await pager.getByRole('button', { name: '第 1 页' }).click();
  await expect(page.locator('.positions-card tbody tr')).toHaveCount(5);
  await expect(pager.getByRole('button', { name: '上一页' })).toBeDisabled();
});

test('navigation moves focus to the page title and tabs keep their own focus', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await expect(page.locator('.page-title')).toBeFocused();

  await page.getByRole('link', { name: '历史与报告', exact: true }).click();
  await expect(page.locator('.page-title')).toBeFocused();
  const ordersTab = page.getByRole('tab', { name: /订单/ });
  await ordersTab.click();
  await expect(ordersTab).toBeFocused();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(3);
});

test('sidebar profile menu opens above the account button and closes with Escape', async ({ page }) => {
  await page.goto('/');
  const trigger = page.getByRole('button', { name: /本机 Owner/ });
  await expect(trigger).toBeVisible();
  await trigger.click();
  const menu = page.getByRole('menu', { name: '个人资料与工作空间' });
  await expect(menu).toBeVisible();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  const triggerBox = await trigger.boundingBox();
  const menuBox = await menu.boundingBox();
  expect(triggerBox && menuBox).toBeTruthy();
  if (triggerBox && menuBox) {
    expect(menuBox.y + menuBox.height).toBeLessThanOrEqual(triggerBox.y + 1);
  }
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await trigger.click();
  await page.getByRole('menuitem', { name: '关于 Stratide' }).click();
  await expect(page.getByRole('heading', { name: '关于' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '关于' })).toHaveAttribute('aria-selected', 'true');
});

test('reduced motion is honoured by system preference and explicit setting', async ({ page }) => {
  const motionVar = () =>
    page.evaluate(() => {
      const raw = getComputedStyle(document.documentElement).getPropertyValue('--motion-drawer').trim();
      const value = parseFloat(raw);
      // Minified CSS may serialize 300ms as .3s; compare durations, not strings.
      return raw.endsWith('ms') ? value : value * 1000;
    });

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  expect(await motionVar()).toBeLessThan(1);
  expect(await page.evaluate(() => {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--motion-modal').trim();
    const value = parseFloat(raw);
    return raw.endsWith('ms') ? value : value * 1000;
  })).toBeLessThan(1);

  await page.goto('/#settings');
  await page.getByRole('button', { name: '减少动效' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'reduce');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.getByRole('button', { name: '跟随系统' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'full');
  expect(await motionVar()).toBe(300);
});

test('drawer and modal really animate, settle into their final state and restore focus', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await expect(page.getByTestId('nav-value')).toBeVisible();
  const trigger = page.locator('.recent-fills-card tbody tr .row-link').first();
  await trigger.click();
  const drawer = page.locator('.drawer');
  await expect(drawer).toBeVisible();
  expect(await drawer.evaluate((el) => el.getAnimations().length)).toBeGreaterThan(0);
  await settleOverlay(page);
  const settled = await drawer.evaluate((el) => {
    const style = getComputedStyle(el);
    return { opacity: style.opacity, transform: style.transform };
  });
  expect(settled.opacity).toBe('1');
  expect(['none', 'matrix(1, 0, 0, 1, 0, 0)']).toContain(settled.transform);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await page.goto('/#agents');
  await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
  const modal = page.locator('.modal');
  await expect(modal).toBeVisible();
  expect(await modal.evaluate((el) => el.getAnimations().length)).toBeGreaterThan(0);
  await settle(page, '.modal');
  const modalState = await modal.evaluate((el) => {
    const style = getComputedStyle(el);
    return { opacity: style.opacity, transform: style.transform };
  });
  expect(modalState.opacity).toBe('1');
  expect(['none', 'matrix(1, 0, 0, 1, 0, 0)']).toContain(modalState.transform);

  const backgroundInert = await page.evaluate(() => document.querySelector('.app-shell')?.hasAttribute('inert') ?? false);
  expect(backgroundInert).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
