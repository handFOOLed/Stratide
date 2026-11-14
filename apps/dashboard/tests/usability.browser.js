import { test, expect } from '@playwright/test';

const base = 'http://127.0.0.1:8736';
const json = (route, data) => route.fulfill({ json: { api_version: 1, data, error: null } });

test('首次离线和详情首次失败都能在原页面重新读取', async ({ page, request }) => {
  const name = '离线恢复测试任务';
  const response = await request.post(base + '/api/agent/tasks', {
    headers: { Origin: base },
    data: {
      name, goal: '合成离线恢复测试', scope: '当前已发布的模拟账户摘要',
      start_day: '2026-10-28', end_day: '2026-11-02', task_budget_micro: null,
    },
  });
  expect(response.ok()).toBeTruthy();
  const { data: task } = await response.json();
  await page.route('**/api/agent/status', (route) => route.abort(), { times: 1 });
  await page.route('**/api/agent/tasks/' + task.id, (route) => route.abort(), { times: 1 });
  await page.goto(base + '/#agents');
  await expect(page.getByText('AI 研究服务不可用')).toBeVisible();
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await expect(page.getByTestId('agent-status-card')).toBeVisible();

  await page.getByTestId('task-row').filter({ hasText: name }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText('无法连接本机研究服务。')).toBeVisible();
  await drawer.getByRole('button', { name: '重新读取', exact: true }).first().click();
  await expect(drawer.getByTestId('task-detail')).toBeVisible();
});

test('预算编辑拒绝超限，保存响应优先于仍在途的旧轮询', async ({ page, request }) => {
  const { data } = await (await request.get(base + '/api/agent/status')).json();
  data.market_budget_caps = { daily_limit_micro: '5000000', monthly_limit_micro: '100000000' };
  const savedBudget = { ...data.budget, daily_limit_micro: '4000000' };
  let saved = false;
  let reads = 0;
  let startOld;
  let releaseOld;
  let releaseFresh;
  const oldStarted = new Promise((resolve) => { startOld = resolve; });
  const old = new Promise((resolve) => { releaseOld = resolve; });
  const fresh = new Promise((resolve) => { releaseFresh = resolve; });

  await page.route('**/api/agent/status', async (route) => {
    reads += 1;
    if (reads === 1) return json(route, data);
    if (!saved) {
      startOld();
      await old;
      return json(route, data).catch(() => {}); // browser may already have aborted
    }
    await fresh;
    return json(route, { ...data, budget: savedBudget }).catch(() => {});
  });
  await page.route('**/api/agent/budget', (route) => {
    expect(route.request().postDataJSON()).toEqual({
      daily_limit_micro: '4000000', monthly_limit_micro: '100000000', confirm_below_committed: false,
    });
    saved = true;
    return json(route, { budget: savedBudget });
  });

  try {
    await page.goto(base + '/#agents');
    await page.getByTestId('budget-edit').click();
    const daily = page.getByTestId('budget-daily');
    const monthly = page.getByTestId('budget-monthly');
    const submit = page.getByTestId('budget-save');
    await daily.fill('10');
    await expect(submit).toBeDisabled();
    await daily.fill('4');
    await monthly.fill('101');
    await expect(submit).toBeDisabled();
    await monthly.fill('100');
    await oldStarted;
    await submit.click();
    await expect(page.getByTestId('agent-budget')).toContainText('¥4.00');
    releaseOld();
    await expect(page.getByTestId('agent-budget')).toContainText('¥4.00');
  } finally {
    releaseOld();
    releaseFresh();
  }
});

test('OpenAI 的连接测试和 DeepSeek 研究及过期价格分别显示', async ({ page }) => {
  const price = {
    state: 'EXPIRED', valid_until: '2020-01-08T00:00:00Z', reviewable: true,
    version: 'fixture-price', source: 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
    input_micro_per_million: '2000000', output_micro_per_million: '8000000',
  };
  let status = {
    provider: 'deepseek', configured_at: null, key_present: true, key_hint: 'sk-••••fake',
    model_installed: true, research_provider: 'deepseek', research_key_present: true,
    research_price: price, budget: null, endpoint: null,
  };
  await page.route('**/api/agent/provider', (route) => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON().provider).toBe('openai');
      status = { ...status, provider: 'openai' };
    }
    return json(route, status);
  });
  await page.route('**/api/agent/provider/test', (route) => {
    expect(route.request().postDataJSON()).toEqual({ provider: 'openai' });
    return json(route, { state: 'OK', provider: 'openai' });
  });
  await page.route('**/api/agent/provider/price-review', (route) => {
    expect(route.request().postDataJSON()).toEqual({ confirmed: true, price_version: 'fixture-price' });
    return json(route, { ...status, research_price: { ...price, state: 'VALID', valid_until: '2099-01-01T00:00:00Z' } });
  });
  await page.goto(base + '/#settings/ai');
  const panel = page.getByTestId('provider-panel');
  await expect(panel.getByText('已过期，付费研究暂停。')).toBeVisible();
  await panel.getByRole('button', { name: 'OpenAI', exact: true }).click();
  await expect(page.getByTestId('provider-test')).toHaveCount(0);
  await page.getByTestId('provider-key').fill('sk-fixture0123456789abcdefghijkl');
  await page.getByTestId('provider-save').click();
  await expect(panel.getByText('OpenAI 官方', { exact: true })).toBeVisible();
  await expect(panel.getByText('DeepSeek 官方', { exact: true })).toBeVisible();
  await page.getByTestId('provider-test').click();
  await expect(panel.getByText(/OpenAI 官方模型列表接口连接成功/)).toBeVisible();
  const renew = page.getByTestId('provider-price-review');
  await expect(renew).toBeDisabled();
  await panel.getByRole('checkbox', { name: /我已核对当前价格/ }).check();
  await renew.click();
  await expect(panel.getByText(/有效至/)).toBeVisible();
});
