import { test, expect } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

test('shared Paper audit links original candidate and orders, NO_FILL, desktop/mobile readonly', async ({page})=>{
  const writes=[];
  page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());});
  await page.route('**/api/v1/account',async route=>{
    const response=await route.fetch(); const body=await response.json();
    body.data.portfolio={automatic:false,policy_version:'fixed-ticket-paper-v1',policy_sha256:'a'.repeat(64),
      target_value_fen:'201000',max_positions:'24',max_daily_orders:'24',pending:null,
      batches:[{decision_day:'20261028',target_day:'20261029',frozen_at:'1793174400000',finalized_at:'1793260800000',
        label:'UNVERIFIED_PAPER_HYPOTHESIS',reason:'NO_FILL_EXPIRED',source_sha256:'b'.repeat(64),calendar_sha256:'c'.repeat(64),
        policy_sha256:'a'.repeat(64),candidate:{task_id:'7',candidate_sha256:'d'.repeat(64),registration_sha256:'e'.repeat(64),model_version:'synthetic-test'},
        order_ids:['1','2'],rejections:[[{market:'Beijing',code:'920001'},'UNSUPPORTED_PAPER']],confirmation_source_sha256:null}]};
    await route.fulfill({json:body});
  });
  await page.route('**/api/v1/orders',async route=>{
    const response=await route.fetch();const body=await response.json();
    body.data=body.data.slice(0,2).map(o=>({...o,status:'Expired',confirmed_filled_shares:'0',reason:'NO_FILL / EXPIRED_DELIVERY_WINDOW'}));
    await route.fulfill({json:body});
  });
  await page.goto('/#overview');
  const card=page.locator('.card').filter({has:page.getByRole('heading',{name:'多证券共享 Paper · 冻结与结算',exact:true})});
  await expect(card.getByText('原候选任务 #7',{exact:false})).toBeVisible();
  await expect(card.getByText('NO_FILL_EXPIRED',{exact:true})).toBeVisible();
  await expect(card.getByText('920001 · 未提交 · UNSUPPORTED_PAPER',{exact:true})).toBeVisible();
  await expect(card.getByText('Owner 已暂停新意图',{exact:false})).toBeVisible();
  const directory=path.resolve('../../state/issue84-ui');mkdirSync(directory,{recursive:true});
  for(const width of [1280,375]){
    await page.setViewportSize({width,height:1000});
    await card.scrollIntoViewIfNeeded();
    expect(await card.evaluate(el=>el.scrollWidth>el.clientWidth+1)).toBe(false);
    await card.screenshot({path:path.join(directory,`portfolio-${width}.png`)});
  }
  expect(writes).toEqual([]);
});
