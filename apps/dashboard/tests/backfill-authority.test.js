import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { mkdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { checklistProgress, checklistVisible, nextChecklistDismissed } from '../src/lib/checklist.ts';
import {
  backfillPresentation,
  marketSummaryFrom,
  mergeMarketRead,
} from '../src/lib/runtimeRefresh.ts';

const readyStatus = {
  setup_complete: true,
  dependencies: {
    tushare_credential: { state: 'CONFIGURED', reason: null, note: null },
    market_eod: { state: 'INITIALIZED', reason: null, note: null },
  },
};

const readyAgent = {
  status: { default_model: 'market-deepseek-fusion', budget: { state: 'configured' } },
};

const fullProgress = { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } };

function checklistFor(market) {
  return checklistProgress({ status: readyStatus, market }, readyAgent);
}

test('84/84 progress cannot override a fresh coverage_complete false', () => {
  const market = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: false,
    last_successful_date: '20261105',
  });
  assert.equal(market.backfillComplete, false);
  assert.equal(market.verification, 'rejected');
  assert.equal(market.downloadPercent, 100);
  const view = backfillPresentation(market, false);
  assert.equal(view.complete, market.backfillComplete);
  assert.equal(view.title, '待校验');
  assert.match(view.text, /校验未通过/);
  assert.equal(view.text.includes('已就绪'), false);
  assert.equal(view.downloadPercent, 100);
  assert.match(view.countText, /已下载 84\/84/);
  const progress = checklistFor(market);
  assert.equal(progress.knownComplete, false);
  assert.equal(progress.knownIncomplete, true);
  assert.equal(checklistVisible(progress, true), true);
  assert.equal(nextChecklistDismissed(progress), false);
});

test('84/84 progress plus a fresh coverage_complete true is verified', () => {
  const market = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: true,
  });
  assert.equal(market.verification, 'verified');
  assert.equal(market.backfillComplete, true);
  const view = backfillPresentation(market, false);
  assert.equal(view.complete, true);
  assert.equal(view.title, '已完成');
  assert.match(view.text, /已就绪/);
  assert.equal(view.downloadPercent, 100);
  const progress = checklistFor(market);
  assert.equal(progress.knownComplete, true);
  assert.equal(checklistVisible(progress, false), false);
  assert.equal(nextChecklistDismissed(progress), true);
});

test('a fuller progress file does not raise the percentage above the fresh report', () => {
  const market = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } },
    { sessions_ready: 10, gaps: [{ day: '20261101' }], coverage_complete: false },
  );
  assert.equal(market.backfillComplete, false);
  assert.equal(market.downloadPercent, 12);
  const view = backfillPresentation(market, false);
  assert.equal(view.downloadPercent, 12);
  assert.match(view.countText, /进度文件 84\/84/);
  assert.equal(view.text.includes('已就绪'), false);
});

test('partial download with coverage_complete false stays incomplete', () => {
  const market = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 20, remaining: 64 } },
    { sessions_ready: 20, gaps: [{ day: '20261101' }], coverage_complete: false },
  );
  assert.equal(market.backfillComplete, false);
  assert.equal(market.verification, 'rejected');
  assert.equal(market.downloadPercent, 24);
  const view = backfillPresentation(market, false);
  assert.equal(view.downloadPercent, 24);
  assert.equal(view.complete, false);
  assert.equal(checklistFor(market).knownIncomplete, true);
});

test('missing coverage flag is not verified even at 84/84', () => {
  const market = marketSummaryFrom(fullProgress, { sessions_ready: 84, gaps: [] });
  assert.equal(market.coverageComplete, null);
  assert.equal(market.verification, 'unknown');
  assert.equal(market.backfillComplete, false);
  const view = backfillPresentation(market, false);
  assert.equal(view.complete, false);
  assert.equal(view.text.includes('已就绪'), false);
  assert.equal(checklistVisible(checklistFor(market), true), true);
});

test('a fresh false replaces a cached verified summary', () => {
  const verified = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: true,
  });
  const rejected = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: false,
  });
  const merged = mergeMarketRead(verified, rejected);
  assert.equal(merged.backfillComplete, false);
  assert.equal(merged.verification, 'rejected');
  assert.equal(checklistVisible(checklistFor(merged), true), true);
  assert.equal(nextChecklistDismissed(checklistFor(merged)), false);
});

test('a failed read does not pair a stale report count with a newer progress percent', () => {
  const rejected = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 10, remaining: 74 } },
    { sessions_ready: 10, gaps: [{ day: '20261101' }], coverage_complete: false },
  );
  const failed = marketSummaryFrom(fullProgress, null, 'MARKET_STATUS_TIMEOUT');
  const merged = mergeMarketRead(rejected, failed);
  assert.equal(merged.backfillComplete, false);
  assert.equal(merged.verification, 'unknown');
  assert.equal(merged.reportSessions, null);
  assert.equal(merged.downloadPercent, 100);
  const view = backfillPresentation(merged, false);
  assert.equal(view.complete, false);
  assert.equal(view.downloadPercent, 100);
  assert.match(view.countText, /已下载 84\/84/);
  assert.equal(view.text.includes('已就绪'), false);
  assert.equal(checklistVisible(checklistFor(merged), true), true);
});

test('repeated status failures do not restore completion from the progress file', () => {
  const verified = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: true,
  });
  const failed = marketSummaryFrom(fullProgress, null, 'MARKET_STATUS_TIMEOUT');
  const once = mergeMarketRead(verified, failed);
  const twice = mergeMarketRead(once, failed);
  assert.equal(once.backfillComplete, false);
  assert.equal(twice.backfillComplete, false);
  assert.equal(twice.statusStale, true);
  assert.equal(twice.verification, 'unknown');
  const view = backfillPresentation(twice, false);
  assert.equal(view.complete, false);
  assert.equal(view.downloadPercent, null);
  assert.match(view.text, /无法读取/);
  assert.equal(view.text.includes('已就绪'), false);
  assert.equal(checklistFor(twice).knownComplete, false);
  assert.equal(checklistVisible(checklistFor(twice), true), true);
});

test('a later true report recovers completion', () => {
  const rejected = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: false,
  });
  const verified = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: true,
  });
  const merged = mergeMarketRead(rejected, verified);
  assert.equal(merged.backfillComplete, true);
  assert.equal(merged.verification, 'verified');
  assert.equal(backfillPresentation(merged, false).title, '已完成');
});

test('a running job is not complete even when the progress file and an old true disagree', () => {
  const runningFalse = marketSummaryFrom(
    { running: true, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } },
    { sessions_ready: 84, gaps: [], coverage_complete: false },
  );
  assert.equal(runningFalse.backfillComplete, false);
  assert.equal(runningFalse.verification, 'rejected');
  const runningView = backfillPresentation(runningFalse, false);
  assert.equal(runningView.title, '进行中');
  assert.equal(runningView.complete, false);
  assert.match(runningView.text, /校验未通过/);

  const runningTrue = marketSummaryFrom(
    { running: true, progress: { sessions: 84, sessions_ready: 40, remaining: 44 } },
    { sessions_ready: 84, gaps: [], coverage_complete: true },
  );
  assert.equal(runningTrue.backfillComplete, false);
  assert.equal(runningTrue.verification, 'unknown');
  assert.equal(backfillPresentation(runningTrue, false).complete, false);
  assert.equal(checklistFor(runningTrue).knownIncomplete, true);
});

test('settings and checklist meters render the conflict without calling it ready', async () => {
  const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '.render-tmp');
  mkdirSync(dir, { recursive: true });
  const outfile = path.join(dir, 'render.js');
  buildSync({
    stdin: {
      contents: `
        import { createElement } from 'react';
        import { renderToStaticMarkup } from 'react-dom/server';
        import { BackfillMeter } from './src/components/domain/BackfillMeter.tsx';
        import { ProgressBar } from './src/components/ui/ProgressBar.tsx';
        export function renderMeter(market) {
          return renderToStaticMarkup(createElement(BackfillMeter, { market, runtimeUnreadable: false }));
        }
        export function renderBar(value, indeterminate, tone, label) {
          return renderToStaticMarkup(createElement(ProgressBar, { value, indeterminate, tone, label }));
        }
      `,
      resolveDir: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
      sourcefile: 'render.tsx',
      loader: 'tsx',
    },
    bundle: true,
    format: 'esm',
    platform: 'node',
    outfile,
    jsx: 'automatic',
    external: ['react', 'react-dom', 'react-dom/server'],
  });
  const rendered = await import(pathToFileURL(outfile).href);
  const conflict = marketSummaryFrom(fullProgress, {
    sessions_ready: 84,
    gaps: [],
    coverage_complete: false,
  });
  const html = rendered.renderMeter(conflict);
  assert.match(html, /data-complete="false"/);
  assert.match(html, /data-verification="rejected"/);
  assert.match(html, /仓库校验未通过/);
  assert.match(html, /100%/);
  assert.equal(html.includes('已就绪'), false);
  assert.match(html, /aria-valuenow="100"/);
  assert.match(html, /progress__bar--warning/);
  assert.match(html, /历史补录下载进度/);

  const unknown = mergeMarketRead(
    marketSummaryFrom(fullProgress, { sessions_ready: 84, gaps: [], coverage_complete: true }),
    marketSummaryFrom({ running: false, progress: null }, null, 'MARKET_STATUS_TIMEOUT'),
  );
  const waiting = rendered.renderMeter(unknown);
  assert.match(waiting, /没有百分比/);
  assert.equal(waiting.includes('aria-valuenow'), false);
  assert.equal(waiting.includes('已就绪'), false);

  const verified = marketSummaryFrom(fullProgress, { sessions_ready: 84, gaps: [], coverage_complete: true });
  const done = rendered.renderMeter(verified);
  assert.match(done, /data-complete="true"/);
  assert.match(done, /已就绪/);
  assert.match(done, /历史补录已校验/);
  rmSync(dir, { recursive: true, force: true });
});
