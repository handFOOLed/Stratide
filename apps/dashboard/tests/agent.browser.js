import { test, expect } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const base = 'http://127.0.0.1:8736';
const evidence = path.resolve(process.env.STRATIDE_UI_EVIDENCE_DIR || '../../state/m2-pr03-browser');
mkdirSync(evidence, { recursive: true });
function readToken() {
  if (process.env.STRATIDE_UI_TEST_TOKEN_FILE) return readFileSync(process.env.STRATIDE_UI_TEST_TOKEN_FILE, 'utf8').trim();
  return JSON.parse(readFileSync(path.resolve('../../state/issue22-browser/session.json'), 'utf8')).token;
}

async function unlock(page) {
  const token = readToken();
  await page.goto(base + '/#agents');
  await page.getByRole('button', { name: '输入 Owner 令牌' }).click();
  await page.getByLabel('本机 Owner 令牌').fill(token);
  await page.getByRole('button', { name: '解锁', exact: true }).click();
  await expect(page.getByText('本机会话已解锁')).toBeVisible();
  const resume = page.getByRole('button', { name: '恢复研究', exact: true });
  if (await resume.isVisible().catch(() => false)) {
    await resume.click();
    await expect(page.getByText('等待或执行已授权研究')).toBeVisible();
  }
  await page.getByLabel('默认模型').selectOption('fake');
  await expect(page.getByLabel('默认模型')).toHaveValue('fake');
  return token;
}

async function createTask(page, name) {
  await page.getByRole('button', { name: '新建任务', exact: true }).click();
  await expect(page.locator('#agent-task-form')).toBeVisible();
  await page.getByLabel('任务名称').fill(name);
  await page.getByLabel('研究目标').fill('核查成本假设和数据来源，并提出可证伪的下一步');
  await page.getByRole('button', { name: '提交研究任务', exact: true }).click();
  await expect(page.locator('#agent-task-form')).not.toBeVisible();
  const row = page.locator('.tasks-table tbody tr').filter({ has: page.getByRole('button', { name, exact: true }) });
  await expect(row).toBeVisible();
  return row;
}

test('real Agent API creates, stores, reads, cancels, pauses and does not call the model for detail views', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const token = await unlock(page);

  const row = await createTask(page, 'Web 持久研究闭环');
  await expect(row).toContainText('已完成');
  const getStatus = async () => (await (await request.get(base + '/api/agent/status', { headers: { 'X-Stratide-Owner': token } })).json()).data;
  const countBefore = (await getStatus()).budget.call_count;

  await row.getByRole('button', { name: 'Web 持久研究闭环', exact: true }).click();
  await expect(page.locator('.drawer')).toContainText('可核查假设');
  await expect(page.locator('.drawer')).toContainText('FAKE / SYNTHETIC');
  expect((await getStatus()).budget.call_count).toBe(countBefore);
  await page.screenshot({ path: path.join(evidence, 'agent-task-drawer-1366.png') });
  await page.getByRole('button', { name: '关闭详情' }).click();

  await page.getByRole('button', { name: '优雅暂停', exact: true }).click();
  // The toast says "已优雅暂停研究"; the runtime badge is the authoritative state.
  await expect(page.locator('.agent-runtime .badge')).toHaveText('已优雅暂停');
  await expect(page.locator('.runtime-title')).toHaveText('已暂停接收新任务');
  const cancelled = await createTask(page, 'Web 排队取消');
  await expect(cancelled).toContainText('排队中');
  await cancelled.getByRole('button', { name: '取消', exact: true }).click();
  await expect(cancelled).toContainText('已取消');
  await page.getByRole('button', { name: '恢复研究', exact: true }).click();
  await expect(page.getByText('等待或执行已授权研究')).toBeVisible();

  expect(errors).toEqual([]);
  expect(JSON.stringify(await page.evaluate(() => [localStorage, sessionStorage]))).not.toContain(token);
  expect(await page.content()).not.toContain(token);
});

test('malicious Provider output stays text and the token is absent from browser persistence', async ({ page }) => {
  const token = await unlock(page);
  await page.getByLabel('默认模型').selectOption('fake-text');
  await expect(page.getByLabel('默认模型')).toHaveValue('fake-text');
  const row = await createTask(page, '恶意文本只读验证');
  await expect(row).toContainText('已完成');
  await row.getByRole('button', { name: '恶意文本只读验证', exact: true }).click();
  await expect(page.locator('.drawer')).toContainText('<img src=x onerror=alert(1)>');
  await expect(page.locator('#drawer img')).toHaveCount(0);
  await page.getByRole('button', { name: '关闭详情' }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: '输入 Owner 令牌' })).toBeVisible();
  expect(JSON.stringify(await page.evaluate(() => [localStorage, sessionStorage]))).not.toContain(token);
  expect(await page.content()).not.toContain(token);
});

test('Agent screenshots at 1366 and 375 plus an honest offline state', async ({ page }) => {
  await unlock(page);
  for (const [width, height] of [[1366, 900], [375, 812]]) {
    await page.setViewportSize({ width, height });
    await expect(page.getByText('研究运行状态')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(evidence, 'agent-' + width + '.png') });
    await page.getByRole('button', { name: '新建任务', exact: true }).click();
    const box = await page.locator('.modal').boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeLessThanOrEqual(width);
      expect(box.x).toBeGreaterThanOrEqual(0);
    }
    await page.screenshot({ path: path.join(evidence, 'agent-modal-' + width + '.png') });
    await page.getByRole('button', { name: '关闭对话框' }).click();
  }

  await page.setViewportSize({ width: 1366, height: 900 });
  await page.route('**/api/agent/**', (route) => route.abort());
  await page.getByRole('button', { name: '刷新研究任务' }).click();
  await expect(page.getByText(/无法连接本机研究服务/).first()).toBeVisible();
});
