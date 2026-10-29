/* Constraint brief: primary saved research tasks and one create action; secondary
   budget headroom/control and model status; tertiary provenance and usage detail.
   Grayscale layout: summary + budget rows, full-width task list, right drawer,
   centered task modal. Existing tokens: 8/12/16/24/32 spacing, 14/16/20 type,
   400/600 weight, 8/12 radius; colors only through existing semantic variables. */
import { esc } from './model.js';
import './agents.css';

const labels = { queued:'排队中', running:'研究中', completed:'已完成', failed:'失败', cancel_requested:'已申请取消', cancelled:'已取消', outcome_uncertain:'结果 / 费用不确定' };
let ownerToken = ''; // Memory only. Never localStorage, URL, markup or logs.
let status = null, tasks = [], nextBefore = null, pageBefore = null, error = null, busy = false;
let renderPage, drawer, modal, detailId = null;
const micro = value => value == null ? '—' : (BigInt(value) / 1000000n).toString() + '.' + (BigInt(value) % 1000000n).toString().padStart(6,'0');
const stateBadge = value => `<span class="badge ${value === 'outcome_uncertain' || value === 'failed' ? 'rejected' : ''}">${esc(labels[value] || value)}</span>`;
const stamp = value => value ? esc(new Date(value).toLocaleString('zh-CN',{hour12:false})) : '—';
const cost = calls => calls?.reduce((s,c)=>s + BigInt(c.state === 'settled' ? c.settled_micro : c.state === 'no_charge' ? '0' : c.maximum_micro),0n).toString() || '0';
function elapsed(task) { return task.started_at && task.finished_at ? `${Math.max(0,Math.round((new Date(task.finished_at)-new Date(task.started_at))/1000))} 秒` : task.started_at ? '运行中' : '—'; }

export function agentView() {
  if (!ownerToken) return `<section class="panel agent-locked"><div class="eyebrow">本机 Owner 控制</div><h2>研究工作空间</h2><p>创建和查看持久研究任务，管理独立于 Paper 账户的研究预算。使用 Agent 目录中的 owner-token 解锁本次浏览器会话。</p><button class="button primary" data-agent="unlock">解锁 Agent 管理</button><p class="help">首次使用：运行启动脚本的 -FakeAgent 选项验证本地流程，或按操作文档保存可信模型与预算配置。密钥仅从后端环境变量读取。</p></section>`;
  if (!status) return `<section class="panel"><h2>研究服务${error ? '不可用' : '连接中'}</h2><p role="status">${esc(error || '读取本地状态…')}</p><button class="button" data-agent="refresh">重新读取</button><button class="text-button" data-agent="lock">锁定</button></section>`;
  const b=status.budget, configured=b.state==='configured';
  const selected=status.models.find(m=>m.id===status.default_model);
  const issue=error || status.worker_error;
  return `<div class="agent-page">${issue ? `<div class="warning" role="alert">${esc(issue)}<span> · 已显示的记录可能不是最新状态</span></div>` : ''}
    <section class="panel agent-summary"><div><div class="eyebrow">研究 Agent V1 · 单 worker</div><h2>${status.paused ? '已优雅暂停' : '等待 / 执行已授权研究'}</h2><p>${status.paused ? '停止开始新任务，已提交调用可完成；仅 Owner 主动恢复。' : '研究不修改账户净值、持仓或策略资格。'}</p>
      <div class="agent-controls"><button class="button" data-agent="${status.paused?'resume':'pause'}" ${busy?'disabled':''}>${status.paused?'恢复研究':'优雅暂停研究'}</button><button class="text-button" data-agent="lock">锁定此会话</button></div></div>
      <div class="agent-budget"><div class="section-heading"><h2>研究预算 <small>${esc(configured ? b.currency : 'unconfigured')}</small></h2><span class="muted">1 单位 = 1,000,000 micro</span></div>${configured ? `<dl class="budget-rows"><dt>今日剩余 / 上限</dt><dd class="numeric">${micro(b.daily_remaining_micro)} / ${micro(b.daily_limit_micro)}</dd><dt>本月剩余 / 上限</dt><dd class="numeric">${micro(b.monthly_remaining_micro)} / ${micro(b.monthly_limit_micro)}</dd><dt>今日 / 本月已核对</dt><dd class="numeric">${micro(b.daily_settled_micro)} / ${micro(b.monthly_settled_micro)}</dd><dt>所有周期未结清预留</dt><dd class="numeric">${micro(b.reserved_micro)}</dd></dl><p class="help">${esc(b.timezone)} · 云端用量是估算，最终账单未核定前保留最大费用。fake 费用为 TST 合成测试值。</p>` : `<p class="warning">日 / 月预算未配置，禁止任何付费调用。额度只由本机 Owner 设置，Web 不提供加额。</p>`}</div></section>
    <section class="panel agent-configuration"><div class="section-heading"><div><h2>模型与自动研究</h2><p>配置切换仅影响新任务；已排队 / 运行任务保留原配置版本。</p></div></div>
      <div class="agent-config-grid"><label>默认模型<select data-agent-select="model" aria-label="默认研究模型" ${busy?'disabled':''}><option value="" disabled ${!status.default_model?'selected':''}>未配置</option>${status.models.map(m=>`<option value="${esc(m.id)}" ${m.id===status.default_model?'selected':''}>${esc(m.label)}</option>`).join('')}</select></label><label>备用配置<select data-agent-select="backup" aria-label="备用研究模型" ${busy?'disabled':''}><option value="" disabled ${!status.backup_model?'selected':''}>未选择</option>${status.models.map(m=>`<option value="${esc(m.id)}" ${m.id===status.backup_model?'selected':''}>${esc(m.label)}</option>`).join('')}</select></label><div><span class="label">EOD 自动研究</span><button class="button" data-agent="eod" ${busy?'disabled':''}>${status.eod.enabled ? '关闭 EOD' : '启用 EOD'}</button><small>${status.eod.enabled?'已启用':'OFF · 默认关闭'} · 仅最新有效源日</small></div></div>
      <div class="source-line"><span class="badge mode">${esc(selected?.kind==='fake'?'FAKE / SYNTHETIC':(selected?.verification||'REAL_PROVIDER_NOT_VERIFIED'))}</span><span>授权：${esc(selected?.authorization || '未配置')}</span><span>最近调用：${esc(selected?.availability||'not_verified')}</span><span>模型 ${esc(selected?.model || '—')}</span><span>费率版本 ${esc(selected?.price_version || '未配置')}</span></div>
      <p class="help">自动备用切换已关闭；不可用时明确失败。需要使用备用配置时，由 Owner 切换默认模型，为后续新任务生效。</p>
      <p class="help">EOD：${esc(status.eod.reason || '尚无触发')} · 最近源日 ${esc(status.eod.latest?.source_day || '—')} ${esc(status.eod.latest?.disposition || '')} · 已记录跳过 ${esc(status.eod.skipped)} 次</p>
      <details class="agent-usage"><summary>调用与模型用量</summary>${configured?`<p>总调用 ${esc(b.call_count)} · 输入 / 输出 Token ${esc(b.input_tokens)} / ${esc(b.output_tokens)} · 收到用量估算 ${micro(b.usage_estimate_micro)} ${esc(b.currency)}</p>`:''}<div class="table-wrap"><table><thead><tr><th>配置</th><th>授权 / 可用性</th><th>调用</th><th>输入 / 输出 Token</th><th>用量估算</th></tr></thead><tbody>${status.models.map(m=>{const u=status.usage_by_model.find(u=>u.provider_id===m.id);return `<tr><td>${esc(m.label)}</td><td>${esc(m.authorization)}</td><td>${esc(u?.calls||'0')}</td><td>${esc(u?.input_tokens||'0')} / ${esc(u?.output_tokens||'0')}</td><td>${micro(u?.usage_micro||'0')}</td></tr>`;}).join('')}</tbody></table></div></details></section>
    <section class="panel agent-tasks"><div class="section-heading"><div><h2>研究任务 <span class="count">${tasks.length}</span></h2><p>查看和刷新只读取本地已保存记录，不调用模型。</p></div><button class="button primary" data-agent="create" ${busy||!selected?'disabled':''}>自定义任务</button></div>
      ${tasks.length ? `<div class="table-wrap"><table><thead><tr><th>任务 / 模型</th><th>状态</th><th>执行时间</th><th>费用或预留</th><th>简短结论</th><th>操作</th></tr></thead><tbody>${tasks.map(t=>`<tr><td><button class="row-link" data-agent="detail" data-id="${t.id}">${esc(t.name)}</button><small>${esc(t.provider_id)}</small></td><td>${stateBadge(t.status)}</td><td>${stamp(t.started_at||t.created_at)}<small>${elapsed(t)}</small></td><td class="numeric">${micro(cost(t.calls))}</td><td class="agent-conclusion">${esc(t.conclusion || t.reason || '等待执行')}</td><td>${actions(t)}</td></tr>`).join('')}</tbody></table></div>` : `<div class="empty"><strong>尚无研究任务</strong><p>从自定义任务开始；或在配置和授权满足后启用每日 EOD。</p></div>`}
      <div class="agent-pagination"><button class="text-button" data-agent="first" ${!pageBefore?'disabled':''}>最新任务</button><button class="text-button" data-agent="next" ${!nextBefore?'disabled':''}>更早任务 →</button><span class="muted">每页最多 20 条</span></div></section>
    <p class="data-footnote">研究输出仅作探索性假设，不是独立策略资格、历史收益认证或实盘部署许可。</p></div>`;
}
function actions(t) {
  return `${['queued','running'].includes(t.status)?`<button class="text-button" data-agent="cancel" data-id="${t.id}" ${busy?'disabled':''}>取消</button>`:''}${t.retryable?`<button class="text-button" data-agent="retry" data-id="${t.id}" ${busy?'disabled':''}>安全重试</button>`:''}`;
}
async function api(path, body) {
  const response=await fetch(`/api/agent/${path}`,{ method:body===undefined?'GET':'POST',cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(8000),
    headers:{'X-Stratide-Owner':ownerToken,...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)}) });
  const payload=await response.json();
  if(!response.ok) throw new Error(payload.error?.code || 'AGENT_API_ERROR');
  return payload.data;
}
async function refresh() {
  if(!ownerToken) return;
  try { const [s,list]=await Promise.all([api('status'),api(`tasks${pageBefore?`?before=${pageBefore}`:''}`)]); status=s; tasks=list.tasks; nextBefore=list.next_before; error=null;
    if(detailId && drawer.open) await detail(detailId,false);
  } catch(e) { error=e.message==='Failed to fetch' ? '本地研究服务离线' : e.message; }
  if(!modal.open) renderPage();
}
function showModal(title,content) {
  modal.innerHTML=`<div class="drawer-heading"><h2 id="agent-modal-title">${title}</h2><button class="icon-button" data-agent="close-modal" aria-label="关闭表单">×</button></div>${content}`;
  modal.showModal();
}
function createModal() {
  const sourceDay=status?.input?.source_day || new Date().toISOString().slice(0,10);
  showModal('自定义研究任务',`<form id="agent-task-form" class="agent-form"><label>任务名称<input name="name" required maxlength="40" placeholder="例如：成本假设复核"></label><label>研究目标<textarea name="goal" required maxlength="650" rows="3" placeholder="写明希望验证的问题与反证条件"></textarea></label><label>证券 / 研究范围<input name="scope" required maxlength="100" placeholder="例如：当前已发布的 Paper 摘要"></label><div class="agent-date-grid"><label>开始日期<input name="start_day" type="date" required value="${esc(sourceDay)}"></label><label>结束日期<input name="end_day" type="date" required value="${esc(sourceDay)}"></label></div><label>单任务预算 micro（可选）<input name="task_budget_micro" inputmode="numeric" pattern="[0-9]+" placeholder="留空仍受日 / 月硬上限"></label><p class="help">输入限于已发布摘要和你填写的课题；日期范围是研究请求，不保证已有该区间完整数据。运行中的取消不能撤销已提交的收费请求。</p><p class="warning" data-form-error hidden></p><div class="agent-form-actions"><button type="button" class="button" data-agent="close-modal">返回</button><button class="button primary" type="submit">提交研究任务</button></div></form>`);
}
async function detail(id,open=true) {
  const t=await api(`tasks/${id}`); detailId=id;
  const r=t.result, result=r?.research;
  drawer.innerHTML=`<div class="drawer-heading"><div><span class="eyebrow">已保存研究任务 #${t.id}</span><h2 id="drawer-title">${esc(t.request.name)}</h2></div><button class="icon-button" data-action="close" aria-label="关闭详情">×</button></div><div class="drawer-body agent-detail">${stateBadge(t.status)} ${actions(t)}
    <dl class="metadata"><dt>原始目标</dt><dd>${esc(t.request.goal)}</dd><dt>研究范围</dt><dd>${esc(t.request.scope)}</dd><dt>请求区间</dt><dd>${esc(t.request.start_day)} — ${esc(t.request.end_day)}</dd><dt>实际摘要源日</dt><dd>${esc(t.input.source_day||'无已发布报告')}</dd><dt>输入模式</dt><dd>${esc(t.input.mode)}</dd><dt>摘要版本</dt><dd class="code">${esc(t.input.version)}</dd><dt>模型 / 配置版本</dt><dd class="code">${esc(t.provider_id)} / ${esc(t.provider_hash)}</dd><dt>创建 / 完成</dt><dd>${stamp(t.created_at)}<br>${stamp(t.finished_at)}</dd><dt>原因</dt><dd>${esc(t.reason||'—')}</dd><dt>取消申请时间</dt><dd>${stamp(t.cancel_requested_at)}</dd></dl>
    ${result?`<div class="source-line"><span class="badge mode">${esc(r.synthetic_provider?'FAKE / SYNTHETIC':'云端文本研究')}</span><span>${esc(r.model)} · ${stamp(r.generated_at)}</span></div><h3>可核查假设</h3><p>${esc(result.hypothesis)}</p>${[['evidence','关键依据'],['risks','反证 / 风险'],['next_steps','下一研究步骤']].map(([key,title])=>`<h3>${title}</h3><ul>${result[key].map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`).join('')}<p class="warning">${esc(r.limitations)}</p>`:'<p class="help">尚无已保存研究输出；此详情读取不会发起推理。</p>'}
    <h3>费用与调用记录</h3><p class="help">云端收到用量仍不是最终账单。未知结果保留最大预留，不自动重发。</p>${t.calls.map(c=>`<div class="agent-call"><strong>#${c.id} · ${esc(c.state)}</strong><p>最大预留 ${micro(c.maximum_micro)} · 已核对 ${micro(c.settled_micro)} · 用量估算 ${micro(c.usage_micro)}</p><small>${esc(c.price_version)} · ${esc(c.day)} / ${esc(c.month)} · ${esc(c.reason||'')}</small></div>`).join('') || '<p>尚未预留 / 发出调用。</p>'}</div>`;
  if(open && !drawer.open) drawer.showModal();
}
export function initAgents(options) {
  renderPage=options.render; drawer=options.drawer;
  modal=document.createElement('dialog'); modal.id='agent-modal'; modal.setAttribute('aria-labelledby','agent-modal-title'); document.body.append(modal);
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-agent]'); if(!button||button.disabled) return;
    const action=button.dataset.agent;
    if(action==='unlock') { showModal('解锁 Agent 管理',`<form id="agent-unlock-form" class="agent-form"><label>本机 Owner 令牌<input type="password" name="token" autocomplete="off" required minlength="32" maxlength="128"></label><p class="help">从本机 Agent 目录的 owner-token 文件复制。只保存在当前页面内存，刷新后需重新解锁。</p><div class="agent-form-actions"><button class="button primary">解锁</button></div></form>`); return; }
    if(action==='lock') { ownerToken=''; status=null; tasks=[]; detailId=null; if(drawer.open) drawer.close(); renderPage(); return; }
    if(action==='close-modal') { modal.close(); return; }
    if(action==='create') { createModal(); return; }
    if(action==='refresh') { await refresh(); return; }
    if(action==='first'||action==='next') { pageBefore=action==='next'?nextBefore:null; await refresh(); return; }
    if(action==='detail') { try { await detail(button.dataset.id); } catch(e) { error=e.message; renderPage(); } return; }
    busy=true;
    try { if(action==='cancel'||action==='retry') await api(`tasks/${button.dataset.id}/${action}`,{});
      else await api('control',{action,...(action==='eod'?{enabled:!status.eod.enabled}:{})});
    } catch(e) { error=e.message; busy=false; renderPage(); return; }
    busy=false; await refresh();
  });
  document.addEventListener('submit',async event=>{
    if(!['agent-unlock-form','agent-task-form'].includes(event.target.id)) return;
    event.preventDefault(); const data=Object.fromEntries(new FormData(event.target));
    if(event.target.id==='agent-unlock-form') { ownerToken=data.token.trim(); modal.close(); await refresh(); return; }
    const submit=event.target.querySelector('[type=submit]'); submit.disabled=true;
    try { data.task_budget_micro=data.task_budget_micro||null; await api('tasks',data); pageBefore=null; modal.close(); await refresh(); }
    catch(e) { const box=event.target.querySelector('[data-form-error]');box.textContent=e.message;box.hidden=false; }
    finally { submit.disabled=false; }
  });
  document.addEventListener('change',async event=>{
    const action=event.target.dataset.agentSelect; if(!action) return;
    try { await api('control',{action,model_id:event.target.value}); await refresh(); } catch(e) { error=e.message;renderPage(); }
  });
  setInterval(()=>{if(location.hash.startsWith('#agents')&&ownerToken&&!modal.open&&!document.hidden&&!busy) refresh();},2500);
}
