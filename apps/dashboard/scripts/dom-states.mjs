import { readFileSync } from 'node:fs';
import { JSDOM, VirtualConsole } from 'jsdom';

// Local acceptance harness for honest empty/invalid/missing-NAV/offline states.
// Requires the fixture servers described in docs/evidence/m2-pr03-ui/README.md.
const EMPTY = process.env.STRATIDE_EMPTY_BASE || 'http://127.0.0.1:8718';
const INVALID = process.env.STRATIDE_INVALID_BASE || 'http://127.0.0.1:8720';
const MISSING_NAV = process.env.STRATIDE_MISSING_NAV_BASE || 'http://127.0.0.1:8719';
const bundle = readFileSync('dist/assets/app.js', 'utf8');
const errors = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const assert = (value, message) => { if (!value) throw new Error(message); };

function mount(base, rejectFetch = false) {
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', (error) => errors.push('jsdom: ' + error.message));
  virtualConsole.on('error', (message) => errors.push('console: ' + String(message)));
  const dom = new JSDOM('<!doctype html><html lang="zh-CN"><head></head><body><div id="root"></div></body></html>', {
    url: base + '/#overview',
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
    if (rejectFetch) return Promise.reject(new Error('connection refused'));
    const url = typeof input === 'string' && input.startsWith('/') ? base + input : input;
    const options = { ...init };
    delete options.signal;
    return globalThis.fetch(url, options);
  };
  window.eval(bundle);
  return { window, doc: window.document };
}
async function waitFor(predicate, label, timeout = 12000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { if (predicate()) return; } catch { /* wait */ }
    await sleep(80);
  }
  throw new Error('timeout: ' + label);
}

{
  const { window, doc } = mount(EMPTY);
  await waitFor(() => doc.body.textContent.includes('尚未选择 Paper 报告'), 'empty');
  assert(!doc.querySelector('[data-testid="nav-value"]'), 'empty has no NAV');
  assert(doc.body.textContent.includes('NO_SNAPSHOT'), 'empty error code');
  window.close();
  console.log('OK empty snapshot');
}
{
  const { window, doc } = mount(INVALID);
  await waitFor(() => doc.body.textContent.includes('Paper 报告不可用'), 'invalid');
  assert(!doc.querySelector('[data-testid="nav-value"]'), 'invalid has no NAV');
  assert(doc.body.textContent.includes('INVALID_SNAPSHOT'), 'invalid error code');
  window.close();
  console.log('OK invalid snapshot');
}
{
  const { window, doc } = mount(MISSING_NAV);
  await waitFor(() => doc.querySelector('[data-testid="nav-value"]')?.textContent === '—', 'missing nav');
  assert(doc.body.textContent.includes('最后估值缺失'), 'missing nav warning');
  assert(doc.body.textContent.includes('缺少可信收盘估值'), 'valuation reason');
  assert(doc.querySelector('.chart-svg'), 'chart renders valid points around gap');
  assert(doc.body.textContent.includes('缺 1 日'), 'chart gap caption');
  window.location.hash = '#settings/data';
  await waitFor(() => doc.body.textContent.includes('数据连接'), 'settings');
  assert(doc.body.textContent.includes('测试专用：缺少可信收盘估值'), 'settings gap reason');
  assert(!doc.body.textContent.includes('[object Object]'), 'gap object not dumped');
  window.close();
  console.log('OK missing NAV + settings gaps');
}
{
  const { window, doc } = mount('http://127.0.0.1:8729', true);
  await waitFor(() => doc.body.textContent.includes('无法连接本地服务'), 'offline');
  assert(!doc.querySelector('[data-testid="nav-value"]'), 'offline has no NAV');
  window.close();
  console.log('OK offline');
}
assert(errors.length === 0, 'console errors: ' + errors.join(' | '));
console.log('ALL STATE CHECKS PASSED');
process.exit(0);