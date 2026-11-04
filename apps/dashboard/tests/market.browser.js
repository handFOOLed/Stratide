import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

test('market EOD shows separate denominators and refreshes local counts at desktop and mobile widths', async ({ page }) => {
  let reads = 0;
  let missingCatalog = false;
  await page.route('**/api/v1/workspace', route => {
    reads++;
    return route.fulfill({json:{data:{schema_version:1,state:'ready',studies:[],evaluations:[],candidates:[],evidence:[],paper_allowed:false,live_allowed:false,
      market:{state:missingCatalog?'BLOCKED':'READY',data_mode:'synthetic_test',last_successful_date:missingCatalog?null:'20261104',gaps:[],latest:{source_day:'20261104',state:missingCatalog?'BLOCKED':'READY',expected_market:missingCatalog?4:5,actual_quoted:missingCatalog?3:4,
        catalog_state:missingCatalog?'NOT_VERIFIED':'VERIFIED',market_denominator_verified:!missingCatalog,catalog_scopes:{BSE:{listed_rows:missingCatalog?0:1}},
        market_explained:missingCatalog?4:5,market_coverage_bps:10000,research_denominator:2,eligible_count:missingCatalog?0:2,categories:{QUOTED:2,UNSUPPORTED:1},
        available_at:'2026-11-04T08:10:00Z',source_states:{daily:'OK'},blockers:[],snapshot_sha256:'a'.repeat(64)}}}}});
  });
  await page.goto('/#history/research');
  const panel = page.getByRole('region', {name:'全市场 EOD 采集'});
  await expect(panel).toContainText('目录内有行情 4/5');
  await expect(panel).toContainText('证券目录范围：已核验');
  await expect(panel).toContainText('研究选样合格 2/2');
  await expect(panel).toContainText('合成测试');
  await page.getByRole('button', {name:'读取资料',exact:true}).click();
  await expect.poll(() => reads).toBe(2);
  const directory = path.resolve('../../state/issue82-ui');
  mkdirSync(directory, {recursive:true});
  for (const width of [1280,375]) {
    await page.setViewportSize({width,height:900});
    await expect(panel).toBeVisible();
    await page.screenshot({path:path.join(directory,`market-${width}.png`),fullPage:true});
    const overflow = await panel.evaluate(el => el.scrollWidth > el.clientWidth + 1);
    expect(overflow).toBe(false);
  }
  missingCatalog = true;
  await page.getByRole('button', {name:'读取资料',exact:true}).click();
  await expect(panel).toContainText('未核验，研究准入受阻');
  await expect(panel).toContainText('100.00%');
  await expect(panel).toContainText('研究选样合格 0/2');
  await expect(panel).not.toContainText('数据覆盖合格');
  for (const width of [1280,375]) {
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:path.join(directory,`market-blocked-${width}.png`),fullPage:true});
    expect(await panel.evaluate(el => el.scrollWidth > el.clientWidth + 1)).toBe(false);
  }
});
