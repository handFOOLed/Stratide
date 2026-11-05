import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

test('independent automation and explicit scope, readonly preview, revoke, desktop/mobile', async ({ page }) => {
  const writes=[];
  const fields=['symbols','risk_forecasts','baselines','source_refs','quality','as_of','output_contract'];
  const data={config:{automatic_timesfm:false,automatic_deepseek:false,candidate_count:8,daily_call_limit:1,
    trading_day_call_limit:1,model_version:'DeepSeek-V4.1-Flash-1017_ALIAS_MUTABLE'},
    grant:null,grant_active:false,grant_sha256:null,model_installed:true,fields,
    recipient:'https://api.deepseek.com/chat/completions',purpose:'market_strategy_research',source_category:'tushare_market_eod',
    budget:{currency:'CNY',daily_remaining_micro:'4803392',monthly_remaining_micro:'99803392'},
    runs:[{source_day:'20261104',state:'TIMESFM_DONE',reason:'REAL_MARKET_DATA_EGRESS_DENIED',cloud_status:'CLOUD_RESEARCH_BLOCKED',
      events:['EOD_RECEIVED','SCREENED','TIMESFM_DONE'],universe_count:5000,qualified_count:30,selected:[{instrument:'600000.SH'}],
      rejection_counts:{CONTINUOUS_HISTORY_OR_ACTION_EVIDENCE_MISSING:4970},candidate_sha256:null,fusion_task_id:null,research:null}]};
  await page.route('**/api/agent/market-research**',route=>{
    const request=route.request();
    if(request.method()==='POST') {
      const action=request.url().split('/').at(-1);const body=request.postDataJSON();writes.push({action,body});
      if(action==='configure') data.config=body;
      if(action==='grant') {data.grant={version:1,authorized_at:'2026-11-04T23:00:00Z',scope:body.scope};data.grant_active=true;data.grant_sha256='a'.repeat(64);}
      if(action==='revoke') data.grant_active=false;
    }
    return route.fulfill({json:{api_version:1,data:request.url().includes('/preview?')?{maximum_micro:'98304',network_calls:0,key_content_read:false,payload:{symbols:['600000.SH']}}:data}});
  });
  const token=JSON.parse(readFileSync(path.resolve('../../state/issue22-browser/session.json'),'utf8')).token;
  await page.goto('/#agents');
  await page.getByRole('button',{name:'输入 Owner 令牌'}).click();
  await page.getByLabel('本机 Owner 令牌').fill(token);
  await page.getByRole('button',{name:'解锁',exact:true}).click();
  await expect(page.getByText('本机会话已解锁')).toBeVisible();
  await page.goto('/#settings/security');
  await expect(page.getByRole('heading',{name:'全市场自动研究',exact:true})).toBeVisible();
  expect(writes).toHaveLength(0);
  await page.getByRole('button',{name:'预览待发 payload 与最坏费用'}).click();
  await expect(page.getByText('本机 payload 预览 · 未发送')).toBeVisible();
  expect(writes).toHaveLength(0);
  await page.getByRole('switch',{name:'自动 TimesFM CPU',exact:true}).click();
  await page.getByRole('switch',{name:'自动 DeepSeek 策略研究',exact:true}).click();
  await page.getByRole('button',{name:'保存研究配置'}).click();
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0].action).toBe('configure');
  await expect(page.getByText('未获有效许可 · REAL_MARKET_DATA_EGRESS_DENIED')).toBeVisible();
  const grant=page.getByRole('button',{name:'确认并保存外发许可'});
  await expect(grant).toBeDisabled();
  await page.getByRole('combobox',{name:'接收方',exact:true}).selectOption('deepseek');
  await page.getByRole('combobox',{name:'来源',exact:true}).selectOption('tushare_market_eod');
  await page.getByRole('combobox',{name:'用途',exact:true}).selectOption('market_strategy_research');
  await page.getByLabel('许可到期（本机时间）').fill('2026-12-01T18:00');
  const checks=page.locator('.market-research-checks input');
  expect(await checks.count()).toBe(7);
  for(const check of await checks.all()){await expect(check).not.toBeChecked();await check.check();}
  await page.getByLabel('我已核对', {exact:false}).check();
  await expect(grant).toBeDisabled();
  await page.getByLabel('我明确授权上述接收方、用途、来源、字段、范围和期限。').check();
  await grant.click();await expect.poll(()=>writes.length).toBe(2);
  expect(writes[1].body.scope.fields).toEqual(fields);
  expect(writes[1].body.scope.context_sessions).toBe(84);
  await expect(page.getByText('许可有效，仅允许已选字段与范围')).toBeVisible();
  await page.getByRole('button',{name:'只读刷新',exact:true}).click();expect(writes).toHaveLength(2);
  const directory=path.resolve('../../state/issue83-ui');mkdirSync(directory,{recursive:true});
  for(const width of [1280,375]){
    await page.setViewportSize({width,height:900});
    await page.screenshot({path:path.join(directory,`market-research-${width}.png`),fullPage:true});
    expect(await page.locator('.market-research-settings').evaluate(el=>el.scrollWidth>el.clientWidth+1)).toBe(false);
  }
  await page.getByRole('button',{name:'撤销未来外发'}).click();await expect.poll(()=>writes.length).toBe(3);
  expect(writes[2].action).toBe('revoke');
  await expect(page.getByText('未获有效许可 · REAL_MARKET_DATA_EGRESS_DENIED')).toBeVisible();
});
