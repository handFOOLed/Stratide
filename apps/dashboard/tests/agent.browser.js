import { test, expect } from '@playwright/test';
import { randomBytes } from 'node:crypto';

/**
 * AI 研究页与通知页的真实 API 回归（fixture 场景 agent，8736）。
 * 该 fixture 使用本地 fake 研究模型 + CNY ¥5/日、¥100/月测试预算；不产生云端调用。
 */
const AGENT = 'http://127.0.0.1:8736';

test.describe.configure({ mode: 'serial' });

async function openAgent(page) {
  await page.goto(AGENT + '/#agents');
  await expect(page.getByTestId('agent-status-card')).toBeVisible();
  // 等首次 agent.status 返回，避免断言落在加载态。
  await expect(page.getByTestId('agent-status-card')).toContainText('运行状态');
  await expect(page.getByTestId('agent-budget')).toBeVisible();
}

async function createTask(page, name) {
  await openAgent(page);
  await page.getByTestId('agent-create').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await page.getByLabel('任务名称').fill(name);
  await page.getByLabel('研究目标').fill('验证浏览器端任务创建、状态展示与任务详情抽屉。');
  await page.getByRole('button', { name: '提交研究', exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

test('AI 研究：运行状态、预算、默认折叠的模型与空研究报告', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await openAgent(page);

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI 研究');
  await expect(page.getByTestId('agent-status-card')).toContainText('运行状态');
  await expect(page.getByTestId('agent-status-card')).toContainText('收盘后自动研究');
  await expect(page.getByTestId('agent-status-card')).not.toContainText('EOD');

  // 预算统一 ¥ 且与账户同一数据源；主界面不出现后端币种/枚举。
  const budget = page.getByTestId('agent-budget');
  await expect(budget).toContainText('¥5.00');
  await expect(budget).toContainText('¥100.00');
  await expect(budget).not.toContainText('CNY');
  await expect(budget).not.toContainText('micro');

  // 模型默认折叠，展开后可设置默认模型。
  const models = page.getByTestId('agent-models');
  await expect(page.getByTestId('agent-default-model')).toHaveCount(0);
  await page.getByTestId('agent-models-toggle').click();
  await expect(page.getByTestId('agent-default-model')).toBeVisible();
  await expect(models).toContainText('默认研究模型');

  // 研究报告空态与诊断折叠。
  await expect(page.getByTestId('agent-reports')).toContainText('还没有研究报告');
  const diagnostics = page.locator('[data-testid="agent-status-card"] details.diagnostics');
  await expect(diagnostics).toHaveJSProperty('open', false);
  await diagnostics.locator('summary').click();
  await expect(diagnostics).toContainText('最近结果');

  expect(errors).toEqual([]);
});

test('新建研究：弹窗初始焦点、空值校验、提交后任务进入列表并可打开详情', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await openAgent(page);

  await page.getByTestId('agent-create').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => document.activeElement?.id)).toBe('task-name');

  await page.getByRole('button', { name: '提交研究', exact: true }).click();
  await expect(dialog).toContainText('请输入任务名称。');
  await expect(dialog).toContainText('请写明研究目标与反证条件。');
  await expect(page.getByRole('dialog')).toHaveCount(1);

  const taskName = '浏览器回归任务';
  await page.getByLabel('任务名称').fill(taskName);
  await page.getByLabel('研究目标').fill('验证浏览器端任务创建、状态展示与任务详情抽屉。');
  await page.getByRole('button', { name: '提交研究', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  const row = page.locator('[data-testid="task-row"]').filter({ hasText: taskName }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText('已完成', { timeout: 30_000 });
  await expect(row).not.toContainText('#');

  await row.click();
  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();
  await expect(drawer.locator('[data-testid="task-detail"]')).toBeVisible();
  await expect(drawer).toContainText('结论与原因');
  await expect(drawer).toContainText('诊断信息');
  const detailDiagnostics = drawer.locator('details.diagnostics');
  await expect(detailDiagnostics).toHaveJSProperty('open', false);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);

  expect(errors).toEqual([]);
});

test('通知：真实任务通知、全部标为已读、查看任务跳转并打开详情', async ({ page, request }) => {
  const name = '通知回归任务 ' + Date.now();
  const created = await request.post(AGENT + '/api/agent/tasks', {
    headers: {
      Accept: 'application/json',
      Origin: AGENT,
      'X-Stratide-Idempotency': randomBytes(16).toString('hex'),
    },
    data: {
      name,
      goal: '验证浏览器端通知列表与已读操作。',
      scope: '当前已发布的模拟账户摘要',
      start_day: '2026-10-28',
      end_day: '2026-11-02',
      task_budget_micro: null,
    },
  });
  expect(created.ok()).toBeTruthy();
  await expect.poll(async () => {
    const response = await request.get(AGENT + '/api/agent/tasks', { headers: { Accept: 'application/json' } });
    const body = await response.json();
    const task = body.data.tasks.find((item) => item.name === name);
    return task ? task.status : null;
  }, { timeout: 30_000 }).toMatch(/completed|failed|cancelled|outcome_uncertain/);

  await page.goto(AGENT + '/#notifications');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('通知');
  await expect(page.locator('.notice-row')).not.toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator('.notice-row').filter({ hasText: name }).first()).toBeVisible();
  await expect(page.locator('.notice-row').filter({ hasText: name }).first()).toContainText('已完成');
  await expect(page.getByText(/\d+ 条未读/).first()).toBeVisible();

  await page.locator('.notice-row').filter({ hasText: name }).first().getByRole('button', { name: '查看任务' }).click();
  await expect(page).toHaveURL(/#agents$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI 研究');
  await expect(page.locator('[data-testid="task-row"]').filter({ hasText: name }).first()).toBeVisible();

  await page.goto(AGENT + '/#notifications');
  const markAll = page.getByRole('button', { name: /全部标为已读|标记本页已读/ });
  await markAll.click();
  await expect(page.locator('.notice-row').filter({ hasText: name })).toHaveCount(0);
  await expect(page.getByText('全部已读', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('通知');
  await expect(page.locator('.notice-row').filter({ hasText: name })).toHaveCount(0);
});
