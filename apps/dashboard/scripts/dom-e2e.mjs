import { readFileSync } from 'node:fs';
import { JSDOM, VirtualConsole } from 'jsdom';

// Local acceptance harness: mounts the built bundle in jsdom and talks to a real
// local Paper + fake-Agent server. It checks functional/state behaviour only;
// real Chromium layout and screenshots are covered by the Playwright tests.
const BASE = process.env.STRATIDE_UI_BASE || 'http://127.0.0.1:8717';
const tokenFile = process.env.STRATIDE_AGENT_TOKEN_FILE || '../../state/agent-ui-test/owner-token';
const token = readFileSync(tokenFile, 'utf8').trim();
const runId = Date.now().toString(36);
const taskName = 'UI 自动化任务 ' + runId;
const queuedName = 'UI 排队取消 ' + runId;
const bundle = readFileSync('dist/assets/app.js', 'utf8');
const errors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', (error) => errors.push('jsdom: ' + error.message));
virtualConsole.on('error', (message) => errors.push('console: ' + String(message)));

setTimeout(() => { console.error('HARD TIMEOUT'); process.exit(2); }, 90000);

const dom = new JSDOM('<!doctype html><html lang="zh-CN"><head></head><body><div id="root"></div></body></html>', {
  url: BASE + '/#overview',
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  virtualConsole,
});
const { window } = dom;
window.matchMedia = (query) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false; } });
class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
window.ResizeObserver = ResizeObserverStub;
window.HTMLElement.prototype.scrollTo = function () {};
window.HTMLElement.prototype.scrollIntoView = function () {};
window.scrollTo = () => {};
window.fetch = (input, init = {}) => {
  const url = typeof input === 'string' && input.startsWith('/') ? BASE + input : input;
  const headers = new Headers(init.headers || {});
  if ((init.method || 'GET') !== 'GET') headers.set('Origin', BASE);
  const options = { ...init, headers };
  delete options.signal;
  return globalThis.fetch(url, options).catch((error) => {
    errors.push('fetch ' + url + ': ' + error.message);
    throw error;
  });
};
window.eval(bundle);

const doc = window.document;
const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
const q = (selector) => doc.querySelector(selector);
const qa = (selector) => Array.from(doc.querySelectorAll(selector));
const bodyText = () => doc.body.textContent.replace(/\s+/g, ' ').trim();
const assert = (value, message) => { if (!value) throw new Error(message); };

async function waitFor(predicate, label, timeout = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { if (predicate()) return; } catch { /* keep waiting */ }
    await sleep(60);
  }
  throw new Error('timeout: ' + label + ' | text=' + bodyText().slice(0, 500));
}
async function goto(hash, label) {
  window.location.hash = hash;
  await waitFor(() => window.location.hash === hash, 'hash ' + hash);
  await sleep(120);
  if (label) await waitFor(() => bodyText().includes(label), label);
}
function click(element) {
  assert(element, 'missing element to click');
  element.click();
}
function findButton(text, root = doc) {
  return Array.from(root.querySelectorAll('button')).find((button) => button.textContent.trim() === text);
}
function fireInput(element, value) {
  const proto = element.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
  element.dispatchEvent(new window.Event('input', { bubbles: true }));
}
function submit(form) {
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
}

await waitFor(() => q('[data-testid="nav-value"]')?.textContent === '¥9,928.93', 'overview nav');
assert(bodyText().includes('账户总览'), 'overview heading');
assert(bodyText().includes('合成测试'), 'mode badge');
assert(bodyText().includes('不是实时行情'), 'non-live label');
assert(!bodyText().includes('查看全部'), 'duplicate overview CTA removed');
assert(!bodyText().includes('查看更多'), 'duplicate more CTA removed');
console.log('OK overview');

await goto('#history/fills', '完整成交');
await waitFor(() => qa('.fills-table tbody tr').length === 2, 'fills rows');
click(q('.fills-table tbody tr .row-link'));
await waitFor(() => q('[role="dialog"]'), 'fill drawer');
assert(bodyText().includes('模拟记账时间'), 'fill drawer time');
assert(bodyText().includes('佣金'), 'fill fee breakdown');
click(q('[aria-label="关闭详情"]'));
await waitFor(() => !q('[role="dialog"]'), 'fill drawer closed');
console.log('OK history fills + drawer');

click(Array.from(doc.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent.includes('订单')));
await waitFor(() => qa('.orders-table tbody tr').length === 3, 'order rows');
assert(bodyText().includes('已拒绝'), 'rejected order');
click(q('.orders-table tbody tr .row-link'));
await waitFor(() => q('[role="dialog"]'), 'order drawer');
assert(bodyText().includes('委托意图不等于实际成交'), 'order drawer note');
click(q('[aria-label="关闭详情"]'));
await waitFor(() => !q('[role="dialog"]'), 'order drawer closed');
console.log('OK history orders + drawer');

click(Array.from(doc.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent.includes('逐日核对')));
await waitFor(() => qa('.daily-table tbody tr').length === 4, 'daily rows');
assert(!q('.chart-svg'), 'no duplicated chart on daily tab');
assert(bodyText().includes('隐含持仓'), 'daily reconciliation');
click(q('.daily-table tbody tr .row-link'));
await waitFor(() => q('[role="dialog"]'), 'day drawer');
assert(bodyText().includes('隐含持仓市值'), 'day drawer');
click(q('[aria-label="关闭详情"]'));
await waitFor(() => !q('[role="dialog"]'), 'day drawer closed');
console.log('OK history daily');

click(Array.from(doc.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent.includes('策略档案')));
await waitFor(() => bodyText().includes('two-signal-example'), 'strategy');
click(q('.data-table tbody tr .row-link'));
await waitFor(() => q('[role="dialog"]'), 'strategy drawer');
assert(bodyText().includes('不可用'), 'strategy unavailable');
click(q('[aria-label="关闭详情"]'));
await waitFor(() => !q('[role="dialog"]'), 'strategy drawer closed');
console.log('OK history strategies');

click(Array.from(doc.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent.includes('研究档案')));
await waitFor(() => bodyText().includes('尚未配置独立研究结果'), 'research empty');
console.log('OK history research');

await goto('#notifications', '通知与审批');
assert(bodyText().includes('通知渠道'), 'notification channels');
assert(bodyText().includes('审批'), 'approval');
assert(bodyText().includes('未接入'), 'honest unconfigured');
console.log('OK notifications');

await goto('#settings', '设置');
assert(bodyText().includes('数据连接'), 'settings data');
assert(bodyText().includes('本机权限边界'), 'settings security');
const darkRadio = doc.querySelector('input[name="stratide-theme"][value="dark"]');
darkRadio.click();
await waitFor(() => doc.documentElement.dataset.theme === 'dark', 'dark theme');
const lightRadio = doc.querySelector('input[name="stratide-theme"][value="light"]');
lightRadio.click();
await waitFor(() => doc.documentElement.dataset.theme === 'light', 'light theme');
const reduceButton = Array.from(doc.querySelectorAll('.segmented__item')).find((button) => button.textContent.trim() === '减少动效');
reduceButton.click();
await waitFor(() => doc.documentElement.dataset.motion === 'reduce', 'reduced motion');
const systemButton = Array.from(doc.querySelectorAll('.segmented__item')).find((button) => button.textContent.trim() === '跟随系统');
systemButton.click();
await waitFor(() => doc.documentElement.dataset.motion === 'full', 'system motion');
console.log('OK settings theme/motion');

await goto('#agents', '解锁本机研究控制');
click(findButton('输入 Owner 令牌'));
await waitFor(() => q('#agent-unlock-form'), 'unlock modal');
const tokenInput = q('#agent-owner-token');
fireInput(tokenInput, token);
submit(q('#agent-unlock-form'));
await waitFor(() => bodyText().includes('本机会话已解锁'), 'agent unlocked', 12000);
const resumeIfNeeded = findButton('恢复研究');
if (resumeIfNeeded) { click(resumeIfNeeded); await waitFor(() => bodyText().includes('等待或执行已授权研究'), 'ensure running', 12000); }
assert(bodyText().includes('TST'), 'budget currency');
assert(!JSON.stringify(window.localStorage).includes(token), 'token absent from localStorage');
assert(!JSON.stringify(window.sessionStorage).includes(token), 'token absent from sessionStorage');
assert(!doc.body.innerHTML.includes(token), 'token absent from DOM');
console.log('OK agent unlock');

click(findButton('新建任务'));
await waitFor(() => q('#agent-task-form'), 'create modal');
fireInput(q('#task-name'), taskName);
fireInput(q('#task-goal'), '验证创建、读取与最终状态，不进行真实模型调用。');
submit(q('#agent-task-form'));
await waitFor(() => !q('#agent-task-form'), 'create modal closed', 12000);
await waitFor(() => qa('.tasks-table tbody tr').some((row) => row.textContent.includes(taskName)), 'task row');
const taskRow = qa('.tasks-table tbody tr').find((row) => row.textContent.includes('UI 自动化任务'));
await waitFor(() => taskRow.textContent.includes('已完成'), 'task completed', 12000);
click(taskRow.querySelector('.row-link'));
await waitFor(() => q('[role="dialog"]') && bodyText().includes('可核查假设'), 'task drawer result', 12000);
assert(bodyText().includes('FAKE / SYNTHETIC'), 'fake label');
assert(!doc.body.innerHTML.includes(token), 'token absent after drawer');
click(q('[aria-label="关闭详情"]'));
await waitFor(() => !q('[role="dialog"]'), 'task drawer closed');
console.log('OK agent create + detail');

click(findButton('优雅暂停'));
await waitFor(() => bodyText().includes('已优雅暂停'), 'paused', 12000);
click(findButton('新建任务'));
await waitFor(() => q('#agent-task-form'), 'create modal 2');
fireInput(q('#task-name'), queuedName);
fireInput(q('#task-goal'), '验证暂停时任务保持排队，并可取消。');
submit(q('#agent-task-form'));
await waitFor(() => !q('#agent-task-form'), 'create modal 2 closed', 12000);
await waitFor(() => qa('.tasks-table tbody tr').some((row) => row.textContent.includes(queuedName) && row.textContent.includes('排队中')), 'queued task', 12000);
const queuedRow = qa('.tasks-table tbody tr').find((row) => row.textContent.includes(queuedName));
click(Array.from(queuedRow.querySelectorAll('button')).find((button) => button.textContent.trim() === '取消'));
await waitFor(() => queuedRow.textContent.includes('已取消'), 'task cancelled', 12000);
console.log('OK agent pause + cancel');
click(findButton('恢复研究'));
await waitFor(() => bodyText().includes('等待或执行已授权研究'), 'resumed', 12000);

await goto('#overview', '账户总览');
await goto('#agents', '研究任务');
assert(bodyText().includes('本机会话已解锁'), 'session persisted across navigation');
click(findButton('锁定'));
await waitFor(() => bodyText().includes('解锁本机研究控制'), 'locked');
console.log('OK agent navigation + lock');

assert(errors.length === 0, 'console errors: ' + errors.join(' | '));
console.log('ALL DOM E2E CHECKS PASSED');
process.exit(0);