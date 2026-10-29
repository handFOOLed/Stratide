import { test,expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
const base='http://127.0.0.1:8716';
const evidence=path.resolve('../../state/issue22-browser');
async function unlock(page) {
  await page.goto(`${base}/#agents`);
  await page.getByRole('button',{name:'解锁 Agent 管理'}).click();
  const {token}=JSON.parse(await readFile(path.join(evidence,'session.json'),'utf8'));
  await page.getByLabel('本机 Owner 令牌').fill(token);
  await page.getByRole('button',{name:'解锁',exact:true}).click();
  await expect(page.getByRole('heading',{name:'研究任务'})).toBeVisible();
}
async function create(page,name) {
  await page.getByRole('button',{name:'自定义任务',exact:true}).click();
  await page.getByLabel('任务名称',{exact:true}).fill(name);
  await page.getByLabel('研究目标',{exact:true}).fill('核查成本假设和数据来源，并提出可证伪的下一步');
  await page.getByLabel('证券 / 研究范围').fill('当前 Paper 摘要');
  await page.getByRole('button',{name:'提交研究任务',exact:true}).click();
  await expect(page.locator('#agent-modal')).not.toBeVisible();
  return page.locator('.agent-tasks tbody tr').filter({has:page.getByRole('button',{name,exact:true})});
}

test('real Agent API creates, stores, reads, cancels, pauses and presents unknown billing honestly',async({page,request})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await unlock(page);
  const navBefore=await (await request.get(`${base}/api/account`)).json();
  if(await page.getByRole('button',{name:'恢复研究',exact:true}).isVisible()) await page.getByRole('button',{name:'恢复研究',exact:true}).click();
  await page.getByLabel('默认研究模型').selectOption('fake');
  const row=await create(page,'Web 持久研究闭环');
  await expect(row).toContainText('已完成',{timeout:10000});
  const {token}=JSON.parse(await readFile(path.join(evidence,'session.json'),'utf8'));
  const getStatus=async()=> (await (await request.get(`${base}/api/agent/status`,{headers:{'X-Stratide-Owner':token}})).json()).data;
  const count=(await getStatus()).budget.call_count;
  await row.getByRole('button',{name:'Web 持久研究闭环',exact:true}).click();
  await expect(page.locator('#drawer')).toContainText('可核查假设');
  await expect(page.locator('#drawer')).toContainText('FAKE / SYNTHETIC');
  expect((await getStatus()).budget.call_count).toBe(count);
  await page.screenshot({path:path.join(evidence,'agent-saved-drawer-1366.png')});
  await page.getByRole('button',{name:'关闭详情'}).click();

  await page.getByRole('button',{name:'优雅暂停研究',exact:true}).click();
  await expect(page.getByRole('heading',{name:'已优雅暂停'})).toBeVisible();
  const cancelled=await create(page,'Web 排队取消');
  await expect(cancelled).toContainText('排队中');await cancelled.getByRole('button',{name:'取消',exact:true}).click();await expect(cancelled).toContainText('已取消');
  await page.getByRole('button',{name:'恢复研究',exact:true}).click();
  await page.getByLabel('默认研究模型').selectOption('fake-unknown');
  const unknown=await create(page,'Web 未知结果不重发');await expect(unknown).toContainText('结果 / 费用不确定',{timeout:10000});
  await expect(unknown.getByRole('button',{name:'安全重试'})).toHaveCount(0);
  expect(BigInt((await getStatus()).budget.reserved_micro)).toBeGreaterThan(0n);
  const navAfter=await (await request.get(`${base}/api/account`)).json();expect(navAfter).toEqual(navBefore);
  expect(errors).toEqual([]);
});

test('malicious Provider output stays text and token is absent from browser persistence',async({page})=>{
  await unlock(page);await page.getByLabel('默认研究模型').selectOption('fake-text');
  const row=await create(page,'恶意文本只读验证');await expect(row).toContainText('已完成',{timeout:10000});
  await row.getByRole('button',{name:'恶意文本只读验证',exact:true}).click();
  await expect(page.locator('#drawer')).toContainText('<img src=x onerror=alert(1)>');await expect(page.locator('#drawer img')).toHaveCount(0);
  const {token}=JSON.parse(await readFile(path.join(evidence,'session.json'),'utf8'));
  expect(await page.evaluate(()=>JSON.stringify([localStorage,sessionStorage]))).not.toContain(token);
  expect(await page.content()).not.toContain(token);
  await page.reload();await expect(page.getByRole('button',{name:'解锁 Agent 管理'})).toBeVisible();
});

test('Agent screenshots and centered structured modal at 1280 and 375, including dark and offline',async({page})=>{
  await unlock(page);
  for(const [width,height] of [[1280,900],[375,812]]) {
    await page.setViewportSize({width,height});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:path.join(evidence,`agent-${width}.png`),fullPage:true});
    await page.getByRole('button',{name:'自定义任务',exact:true}).click();
    const box=await page.locator('#agent-modal').boundingBox();expect(Math.abs(box.x+box.width/2-width/2)).toBeLessThan(3);
    await page.screenshot({path:path.join(evidence,`agent-modal-${width}.png`)});
    await page.getByRole('button',{name:'关闭表单'}).click();
  }
  await page.setViewportSize({width:1280,height:900});await page.getByLabel('主题',{exact:true}).selectOption('dark');await page.screenshot({path:path.join(evidence,'agent-dark-1280.png'),fullPage:true});
  await page.route('**/api/agent/**',route=>route.abort());await expect(page.getByRole('alert')).toContainText('离线',{timeout:10000});
});
