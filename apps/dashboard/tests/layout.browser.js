import { test, expect } from '@playwright/test';

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
      workspaceScrollTop: workspace ? workspace.scrollTop : null,
      scrollbarGutter: workspace ? getComputedStyle(workspace).scrollbarGutter : null,
      bodyOverflow: getComputedStyle(document.body).overflow,
      docScrollWidth: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      activePage: document.querySelector('.nav-item[aria-current="page"]')?.textContent?.trim() ?? null,
    };
  });
}

function closeTo(a, b, tolerance = 0.75) {
  expect(a).not.toBeNull();
  expect(b).not.toBeNull();
  expect(Math.abs(a - b)).toBeLessThanOrEqual(tolerance);
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
    await expect(page.getByRole('heading', { name: '数据连接' })).toBeVisible();
    const settings = await measure(page);

    for (const state of [overview, history, agents, settings]) {
      expect(state.scrollbarGutter).toBe('stable');
      expect(state.bodyOverflow).toBe('hidden');
      expect(state.docScrollWidth).toBeLessThanOrEqual(state.viewport);
    }

    closeTo(overview.innerX, history.innerX);
    closeTo(history.innerX, agents.innerX);
    closeTo(agents.innerX, settings.innerX);
    closeTo(overview.innerWidth, history.innerWidth);
    closeTo(history.innerWidth, agents.innerWidth);
    closeTo(overview.titleX, overview.cardX);
    closeTo(history.titleX, history.cardX);
    closeTo(agents.titleX, agents.cardX);
    closeTo(settings.titleX, settings.cardX);
    if (width >= 960) {
      closeTo(overview.breadcrumbX, overview.titleX);
      closeTo(history.breadcrumbX, history.titleX);
      closeTo(agents.breadcrumbX, agents.titleX);
      closeTo(settings.breadcrumbX, settings.titleX);
    }
    if (width >= 960) {
      closeTo(history.tabsX, history.cardX);
    }

    // Drawer and modal must not change the content baseline or the gutter.
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

    // Dark theme must not move the baseline either.
    const beforeTheme = await measure(page);
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const withTheme = await measure(page);
    closeTo(beforeTheme.titleX, withTheme.titleX);
    closeTo(beforeTheme.cardX, withTheme.cardX);
    closeTo(beforeTheme.workspaceClientWidth, withTheme.workspaceClientWidth);
    await page.getByRole('button', { name: '切换到浅色主题' }).click();

    if (width === 1366) {
      expect(history.workspaceScrollHeight).toBeGreaterThan(history.workspaceClientHeight);
      expect(overview.workspaceScrollHeight).toBeGreaterThan(overview.workspaceClientHeight);
      expect(agents.workspaceScrollHeight).toBeGreaterThanOrEqual(agents.workspaceClientHeight);
    }
  }
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

test('reduced motion is honoured by system preference and explicit setting', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--motion-drawer').trim())).toBe('0.01ms');
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--motion-modal').trim())).toBe('0.01ms');

  await page.goto('/#settings');
  await page.getByRole('button', { name: '减少动效' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'reduce');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.getByRole('button', { name: '跟随系统' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion', 'full');
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--motion-drawer').trim())).toBe('300ms');
});