/* Constraint brief (PR #15 Q01–31, Q66–69):
   Primary: one account's NAV and asset curve. Secondary: cash, P&L, holdings,
   recorded strategy and confirmed fills. Tertiary: provenance and health.
   Primary action: reconnect to the pinned report; no financial actions.
   Grayscale structure: 1:2 summary/chart, 1:1 strategy/positions, full-width fills.
   Tokens: 4/8/12/16/24/32/48px spacing, 12/14/16/20/24/36px type,
   400/600 weight, 8/12px radius. Semantic colors are applied after structure. */
import './tokens.css';
import './styles.css';
import { agentView, initAgents } from './agents.js';
import { RANGES, METRICS, MODES, STATUS, money, bps, shares, signClass, esc, day, timestamp,
  instrument, preference, remember, rangeRows, sortRows, chartModel } from './model.js';

const root = document.querySelector('#app');
const drawer = document.querySelector('#drawer');
const pages = { overview: '总览', history: '历史与报告', agents: 'Agent 管理', notifications: '通知与审批', settings: '设置' };
const icons = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-7M3 4v5h5M12 7v6l4 2"/>',
  agents: '<rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8M1 11v5M23 11v5"/>',
  notifications: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  settings: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2"/><circle cx="12" cy="12" r="5"/>',
};
function icon(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5">${icons[name] || icons.overview}</svg>`; }
const state = {
  data: null, meta: null, error: null, research: null, researchError: null, loading: true, online: false,
  range: preference('range', '30D', RANGES), metric: preference('metric', 'nav', Object.keys(METRICS)),
  theme: preference('theme', 'system', ['light', 'dark', 'system']),
  expanded: { strategies: false, positions: false },
  sort: { strategies: preference('sort.strategies', 'name:asc'), positions: preference('sort.positions', 'name:asc') },
};

function applyTheme() {
  document.documentElement.dataset.theme = state.theme === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : state.theme;
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (state.theme === 'system') applyTheme(); });
applyTheme();

function route() {
  const [page, tab] = location.hash.slice(1).split('/');
  return { page: Object.hasOwn(pages, page) ? page : 'overview', tab: ['fills', 'orders', 'performance', 'research'].includes(tab) ? tab : 'fills' };
}
const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
const empty = (title, detail) => `<div class="empty"><span class="empty-mark" aria-hidden="true">—</span><strong>${esc(title)}</strong><p>${esc(detail)}</p></div>`;
const signed = value => `<span class="numeric ${signClass(value)}">${money(value, true)}</span>`;
function sourceNote() {
  const m = state.meta;
  if (!m) return '';
  return `<div class="source-line">${badge(MODES[m.mode] || m.mode, 'mode')}<span class="code">${esc(m.mode)}</span><span>源日 ${day(m.last_day)}</span><span>最后一次发布的快照 · 非实时同步</span></div>`;
}

function shell(content) {
  const { page } = route();
  root.innerHTML = `<div class="shell"><aside class="sidebar">
    <a class="brand" href="#overview" aria-label="Stratide 总览"><span class="brand-mark">S</span><span>Stratide<small>Paper workspace</small></span></a>
    <div class="nav-label">工作空间</div><nav aria-label="主导航">${Object.entries(pages).map(([key, name]) => `<a href="#${key}" class="nav-item ${page === key ? 'active' : ''}" ${page === key ? 'aria-current="page"' : ''}>${icon(key)}<span>${name}</span></a>`).join('')}</nav>
    <div class="sidebar-footer"><span class="local-dot"></span><span>本地工作空间<small>Paper 只读 · 研究可控</small></span></div>
    </aside><div class="workspace"><header class="topbar"><div class="breadcrumb">工作空间 <span>/</span> <strong>${pages[page]}</strong></div>
      <div class="topbar-actions">${badge('PAPER ONLY', 'paper')}
      <details class="health"><summary><span class="status-dot ${state.online ? 'online' : ''}"></span>${state.loading ? '连接中' : state.online ? '服务可达' : '连接离线'}<span aria-hidden="true">⌄</span></summary>
        <div class="health-panel"><strong>本地服务状态</strong><dl><dt>Web 服务</dt><dd>${state.online ? '本次请求成功' : '当前无法连接'}</dd><dt>市场数据</dt><dd>已发布快照，非实时</dd><dt>风控</dt><dd>仅展示报表记录</dd><dt>前向账户</dt><dd>尚无前向模拟账户</dd><dt>研究 Agent</dt><dd>独立研究控制页</dd><dt>通知服务</dt><dd>尚未实现</dd></dl></div></details>
      <label class="theme-picker"><span class="sr-only">主题</span><select aria-label="主题" data-theme-select>${[['system','跟随系统'],['light','浅色'],['dark','深色']].map(([key,name]) => `<option value="${key}" ${state.theme === key ? 'selected' : ''}>${name}</option>`).join('')}</select></label></div></header>
      <main id="main"><div class="page-heading"><div><h1>${page === 'overview' ? '账户总览' : pages[page]}</h1><p>${page === 'overview' ? '一处查看 Paper 账户的资产、持仓与模拟成交。' : page === 'history' ? '沿同一账户查看交易与表现，独立查阅研究结果。' : 'Stratide 本地 Paper 工作空间'}</p></div><button class="button" data-action="reload" ${state.loading ? 'disabled' : ''}>↻ 重新连接</button></div>
      ${sourceNote()}${content}<footer class="page-footer"><span>Stratide · 本地 Paper Dashboard V1</span><span>尚无前向模拟账户 · 研究不改变账户资产</span></footer></main></div></div>`;
}

function unavailable() {
  if (state.loading) return `<div class="skeleton-grid" aria-label="正在加载账户"><div class="skeleton"></div><div class="skeleton"></div></div>`;
  const noInput = state.error?.code === 'NO_SNAPSHOT';
  return `<section class="panel error-panel" role="status">${empty(noInput ? '尚未选择 Paper 报告' : state.error?.code === 'OFFLINE' ? '无法连接本地服务' : 'Paper 报告不可用',
    state.error?.message || '没有可读取的账户数据。')}<p class="help">${noInput ? '启动时指定一个既有完整六报告目录，再打开此页面。' : '修复报告或连接后点击“重新连接”。服务只在启动时读取报告，更新快照请显式重启。'}</p></section>`;
}

function summary() {
  const a = state.data.account;
  return `<article class="panel account-summary"><div class="eyebrow">账户净值 <span class="muted">CNY</span></div><div class="hero-value numeric" data-testid="nav-value">${money(a.nav_fen)}</div>
    <div class="account-name">${esc(a.account_id)}</div><dl class="cash-rows"><dt>账户现金</dt><dd class="numeric">${money(a.cash_fen)}</dd><dt>可用现金</dt><dd class="numeric">${money(a.available_cash_fen)}</dd><dt>订单预留</dt><dd class="numeric">${money(a.reserved_cash_fen)}</dd></dl>
    <div class="pnl-grid"><div><div class="label">当日盈亏 <small>源日</small></div>${signed(a.session_pnl_fen)}</div><div><div class="label">累计盈亏</div>${signed(a.cumulative_pnl_fen)}</div></div>
    <div class="valuation-note">最后有效估值<br><strong>${state.meta.last_valid_valuation_at ? timestamp(state.meta.last_valid_valuation_at) : day(state.meta.as_of)}</strong><small>Asia/Shanghai · EOD</small></div>
    ${a.valuation_error ? `<div class="warning" role="status">估值缺失：${esc(a.valuation_error)}。净值与相关盈亏不可用。</div>` : ''}
  </article>`;
}

function chartGraphic(rows, width) {
  const model = chartModel(rows, state.metric, width);
  const format = value => state.metric === 'return' ? bps(value) : money(value);
  let graphic = empty('此区间没有有效估值', '缺失估值保留为空，不生成收益点或填充日期。');
  if (model) {
    graphic = `<svg class="equity-chart" viewBox="0 0 ${width} 270" role="img" aria-label="当前 Paper 账户${METRICS[state.metric]}曲线，${rows.length}个报告日期">
      ${model.ticks.map((t, i) => `<line class="grid-line" x1="100" x2="${width-16}" y1="${t.y}" y2="${t.y}"/><text class="axis-label" x="88" y="${t.y + 4}" text-anchor="end">${model.ticks.some((other,j) => j < i && other.value === t.value) ? '' : esc(format(t.value))}</text>`).join('')}
      ${model.paths.map(d => `<path class="chart-line" d="${d}"/>`).join('')}
      ${model.points.filter(Boolean).map(p => `<circle class="chart-point" cx="${p.x}" cy="${p.y}" r="3.5"><title>${day(p.day)} · ${esc(format(p.value))}</title></circle>`).join('')}
      <text class="axis-label" x="100" y="259">${day(rows[0].day)}</text><text class="axis-label" x="${width-16}" y="259" text-anchor="end">${day(rows.at(-1).day)}</text></svg>`;
  }
  return graphic;
}
function chart() {
  const rows = rangeRows(state.data.equity, state.range);
  return `<section class="panel chart-panel"><div class="section-heading"><h2>资产表现</h2><div class="segment" role="group" aria-label="图表指标">${Object.entries(METRICS).map(([key,name]) => `<button data-action="metric" data-value="${key}" aria-pressed="${state.metric === key}" class="${state.metric === key ? 'selected' : ''}">${name}</button>`).join('')}</div></div>
    <div class="chart-toolbar"><div class="legend"><span class="legend-line"></span>当前 Paper 账户</div><div class="range-picker" role="group" aria-label="时间范围">${RANGES.map(r => `<button data-action="range" data-value="${r}" class="${state.range === r ? 'selected' : ''}" aria-pressed="${state.range === r}">${r}</button>`).join('')}</div></div>
    <div class="chart-canvas">${chartGraphic(rows,940)}</div><div class="chart-caption"><span>${rows.length} 个报告日期 · ${rows.filter(r => r.nav_fen !== null).length} 个有效 NAV 点${rows.some(r=>r.nav_fen === null) ? ` · 缺估值 ${rows.filter(r=>r.nav_fen === null).length} 日` : ''}${state.metric === 'return' ? ' · 收益率沿用整数基点精度' : ''}</span><span>仅按真实日期绘制 · 不补齐区间</span></div></section>`;
}

function column(kind, key, name) {
  const [current, direction] = state.sort[kind].split(':');
  const arrow = current !== key ? '↕' : direction === 'asc' ? '↑' : '↓';
  return `<th scope="col" ${current === key ? `aria-sort="${direction === 'asc' ? 'ascending' : 'descending'}"` : ''}><button data-action="sort" data-kind="${kind}" data-key="${key}">${name}<span aria-hidden="true">${arrow}</span></button></th>`;
}

function compactList(kind) {
  const strategy = kind === 'strategies';
  const data = strategy ? state.data.strategies.map(s => ({ ...s, name: s.deployment.strategy_id, status: '快照记录', pnl: s.pnl_fen, drawdown: s.drawdown_bps }))
    : state.data.positions.map(p => ({ ...p, name: p.instrument.code, value: p.market_value_fen, pnl: p.unrealized_pnl_fen, trend: null }));
  let [key, direction] = state.sort[kind].split(':');
  if (!['name','status','pnl','drawdown','value','trend'].includes(key) || !['asc','desc'].includes(direction)) { key = 'name'; direction = 'asc'; }
  const sorted = sortRows(data, key, direction);
  const visible = state.expanded[kind] ? sorted : sorted.slice(0, 5);
  return `<section class="panel compact-panel"><div class="section-heading"><div><h2>${strategy ? '策略记录' : '当前持仓'}<span class="count">${data.length}</span></h2><p>${strategy ? '报表策略 · 运行状态未接入' : '源日持仓与可卖数量'}</p></div>${data.length > 5 ? `<button class="text-button" data-action="expand" data-kind="${kind}">${state.expanded[kind] ? '收起' : '展开全部'}</button>` : ''}</div>
    ${data.length ? `<div class="table-wrap"><table class="compact-table"><thead><tr>${strategy ? column(kind,'name','名称')+column(kind,'status','状态')+column(kind,'pnl','收益')+column(kind,'drawdown','回撤') : column(kind,'name','证券')+column(kind,'value','市值')+column(kind,'pnl','浮动盈亏')+column(kind,'trend','走势')}</tr></thead><tbody>${visible.map(row => `<tr data-action="detail" data-kind="${kind}" data-index="${data.indexOf(row)}" tabindex="0" aria-label="查看${esc(row.name)}详情"><td><button class="row-link" data-action="detail" data-kind="${kind}" data-index="${data.indexOf(row)}">${esc(row.name)}</button><small>${esc(strategy ? row.deployment.group_id : row.instrument.market)}</small></td>${strategy ? `<td>${badge('快照记录')}</td><td class="numeric">—</td><td class="numeric">—</td>` : `<td class="numeric">${money(row.market_value_fen)}</td><td>${signed(row.unrealized_pnl_fen)}</td><td class="unavailable-value" title="六报告没有行情序列">—</td>`}</tr>`).join('')}${!state.expanded[kind] && visible.length < 5 ? `<tr class="table-spacer" aria-hidden="true"><td colspan="4" data-space="${5-visible.length}"></td></tr>` : ''}</tbody></table></div>` : empty('当前空仓', '此报告没有持仓记录。没有生成占位证券。')}
    <div class="panel-footnote">${strategy ? '收益与回撤无独立归因数据 · 点击查看冻结版本' : '行情走势尚不可用 · 点击查看股数、成本与关联成交'}</div></section>`;
}

function fillsTable(recent = false) {
  const rows = [...state.data.fills].reverse().slice(0, recent ? 5 : undefined);
  if (!rows.length) return empty('尚无已确认模拟成交', '未成交、拒绝和过期订单可在订单状态中查看。');
  return `<div class="table-wrap"><table class="trade-table"><thead><tr>${['模拟记账时间','证券','方向','价格','数量 / 股','费用','所属策略'].map(h => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(f => `<tr><td>${day(f.day)}<small>${timestamp(f.simulated_at)}</small></td><td>${esc(instrument(f.instrument))}</td><td>${badge(f.side === 'Buy' ? '买入' : '卖出', f.side === 'Buy' ? 'buy' : 'sell')}</td><td class="numeric">${money(f.price_fen)}</td><td class="numeric">${shares(f.quantity)}</td><td class="numeric">${money(f.fee_fen)}</td><td class="strategy-cell" title="${esc(f.deployment.frozen_version)}">${esc(f.deployment.strategy_id)}</td></tr>`).join('')}</tbody></table></div>`;
}

function ordersTable() {
  if (!state.data.orders.length) return empty('尚无模拟订单', '账户报告中没有提交过订单。');
  return `<div class="table-wrap"><table class="orders-table"><thead><tr>${['订单 / 源日','证券 / 方向','委托数量','已确认 / 剩余','限价','状态','原始原因'].map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${[...state.data.orders].reverse().map(o => `<tr><td class="numeric">#${esc(o.order_id)}<small>${day(o.day)}</small></td><td>${esc(instrument(o.instrument))}<small>${o.side === 'Buy' ? '买入' : '卖出'}</small></td><td class="numeric">${shares(o.quantity)}</td><td class="numeric">${shares(o.confirmed_filled_shares)} / ${shares(o.remaining)}</td><td class="numeric">${money(o.limit_fen)}</td><td>${badge(STATUS[o.status] || o.status, o.status === 'Rejected' ? 'rejected' : '')}</td><td class="reason">${esc(o.reason || '无额外原因')}</td></tr>`).join('')}</tbody></table></div>`;
}

function overview() {
  if (!state.data) return unavailable();
  const risk = state.data.account.risk;
  const frozen = (risk?.account_freezes?.length || 0) + (risk?.strategy_freezes?.length || 0);
  return `${frozen ? `<div class="warning risk-banner" role="alert">⚠ 此快照记录了 ${frozen} 项账户或策略风控锁。这里只展示原报告状态，服务可达不代表风控已恢复。</div>` : ''}<div class="overview-top">${summary()}${chart()}</div><div class="two-columns">${compactList('strategies')}${compactList('positions')}</div>
    <section class="panel recent-fills"><div class="section-heading"><div><h2>最近模拟成交</h2><p>仅已确认的 fills · 最近最多五笔</p></div><a class="text-button" href="#history/fills">查看全部 →</a></div>${fillsTable(true)}</section>
    <div class="data-footnote"><span class="info-icon">i</span><p>${state.meta.mode === 'synthetic_test' ? '当前展示仓库合成测试报告，仅验证软件行为。' : '当前展示历史 EOD 模拟结果，历史可用时间未获 point-in-time 核验。'} 本页面未连接持续运行的前向 Paper 账户。</p></div>`;
}

function researchView() {
  if (state.researchError) return `<div class="warning" role="status">独立研究结果不可用：${esc(state.researchError.message)}</div>`;
  const results = state.research?.results || [];
  if (!results.length) return empty('尚未配置独立研究结果', '使用启动参数 --evaluation-file 指定一个本机已保存的 evaluation.json。研究数据始终独立于账户净值。');
  return results.map(r => `<div class="research-result"><div class="section-heading"><div><h2>独立研究结果</h2><p>${esc(r.strategy_version || '已保存研究')}</p></div>${badge('不计入账户 NAV', 'mode')}</div><div class="research-labels">${badge(r.research_evidence)}${badge(r.engineering)}${badge(`独立验收：${typeof r.independent_acceptance === 'string' ? r.independent_acceptance : '见原研究报告'}`)}</div>
    <p class="muted">${esc(r.data_coverage?.target || '历史研究')} · 目标长窗口 ${esc(r.data_coverage?.target_blockers?.length ? 'DATA_BLOCKED' : '状态见原研究报告')}。页面读取已保存结论，不重新评价策略。</p>
    <div class="table-wrap"><table><thead><tr>${['区段','日期','交易日','净变化','模拟成交','缺估值日'].map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${r.windows.map(w=>`<tr><td>${esc(w.name)}</td><td>${day(w.first_day)} — ${day(w.last_day)}</td><td class="numeric">${shares(w.days)}</td><td>${signed(w.net_pnl_fen)}</td><td class="numeric">${shares(w.fills)}</td><td class="numeric">${shares(w.missing_nav_days)}</td></tr>`).join('')}</tbody></table></div><p class="panel-footnote">这是独立研究档案，不能作为当前账户资金、持续前向表现或已获准入的证明。</p></div>`).join('');
}

function history() {
  const { tab } = route();
  return `<div class="tabs" role="tablist" aria-label="历史与报告">${[['fills','交易记录'],['performance','账户表现'],['research','研究与回测']].map(([key,name])=>`<a role="tab" href="#history/${key}" aria-selected="${key === tab || key === 'fills' && tab === 'orders'}">${name}</a>`).join('')}</div>
    ${tab === 'research' ? `<section class="panel history-panel">${researchView()}</section>` : !state.data ? unavailable() : tab === 'performance' ? `<div class="performance-summary"><div><span>累计收益率</span><strong class="numeric ${signClass(state.data.account.total_return_bps)}">${bps(state.data.account.total_return_bps)}</strong></div><div><span>每日观察最大回撤</span><strong class="numeric">${bps(state.data.account.max_daily_observation_drawdown_bps).replace('+','')}</strong></div><div><span>累计模拟费用</span><strong class="numeric">${money(state.data.account.total_fee_fen)}</strong></div><div><span>对比基准</span><strong>无同期基准序列</strong></div></div>${chart()}
      <section class="panel history-panel"><div class="section-heading"><h2>账户每日记录</h2><span class="muted">同一账户 · ${state.data.equity.length} 个源日期</span></div><div class="table-wrap"><table><thead><tr>${['源日期','账户净值','现金','累计盈亏','累计收益率','估值状态'].map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${[...state.data.equity].reverse().map(d=>`<tr><td>${day(d.day)}</td><td class="numeric">${money(d.nav_fen)}</td><td class="numeric">${money(d.cash_fen)}</td><td>${signed(d.cumulative_pnl_fen)}</td><td class="numeric">${bps(d.return_bps)}</td><td>${esc(d.valuation_error || '有效')}</td></tr>`).join('')}</tbody></table></div></section>` : `<section class="panel history-panel"><div class="section-heading"><div class="segment" role="group" aria-label="交易记录类型"><a href="#history/fills" class="${tab === 'fills' ? 'selected' : ''}">已确认成交 (${state.data.fills.length})</a><a href="#history/orders" class="${tab === 'orders' ? 'selected' : ''}">订单状态 (${state.data.orders.length})</a></div><span class="muted">${tab === 'orders' ? '委托意图不等于实际成交' : '模拟成交 · 非券商成交'}</span></div>${tab === 'orders' ? ordersTable() : fillsTable()}</section>`}`;
}

function settings() {
  const m = state.meta;
  return `<section class="panel settings-panel"><h2>外观</h2><p>浅色、深色或跟随系统，选择保存在当前浏览器。</p><div class="segment" role="group" aria-label="主题设置">${[['system','跟随系统'],['light','浅色'],['dark','深色']].map(([key,name])=>`<button data-action="theme" data-value="${key}" aria-pressed="${state.theme === key}" class="${state.theme === key ? 'selected' : ''}">${name}</button>`).join('')}</div></section>
    <section class="panel settings-panel"><h2>数据连接</h2><p>启动参数指定一个已发布的权威 Paper 六报告目录。页面重新连接只读取当前内存快照；更换报告或更新内容后，使用指定目录重启服务。</p><dl class="metadata"><dt>账户状态</dt><dd>${m ? '已加载只读快照' : '尚未加载报告'}</dd><dt>数据源版本</dt><dd>${esc(m?.source_version || '未配置')}</dd><dt>证据等级</dt><dd>${esc(m?.evidence_class || '不可用')}</dd><dt>验证范围</dt><dd>六报告结构与一致性；不代表独立账本重新验收</dd><dt>报告区间</dt><dd>${m ? `${day(m.first_day)} — ${day(m.last_day)}` : '—'}</dd><dt>快照摘要</dt><dd class="code">${esc(m?.snapshot_id || '—')}</dd><dt>账本尾摘要</dt><dd class="code">${esc(m?.ledger_head || '—')}</dd><dt>前向模拟</dt><dd>尚无前向模拟账户</dd></dl></section>
    <section class="panel settings-panel"><h2>连接与权限设置</h2>${empty('可信本机研究设置', '服务仅绑定 127.0.0.1。Paper 账户保持只读；模型、预算、授权在本机 Agent settings.json 设置，密钥从环境变量读取。Web 研究控制需 Owner 令牌；通知连接尚未接入。')}</section>`;
}

function render() {
  const { page } = route();
  const content = page === 'overview' ? overview() : page === 'history' ? history() : page === 'settings' ? settings()
    : page === 'agents' ? agentView()
    : `<div class="notification-columns"><section class="panel"><div class="section-heading"><h2>通知</h2>${badge('尚未实现')}</div>${empty('通知服务尚未接入', '没有已配置的通知渠道，也不声称发送过任何消息。')}</section><section class="panel"><div class="section-heading"><h2>审批</h2>${badge('尚未实现')}</div>${empty('审批服务尚未接入', '当前只读服务没有业务审批或预算修改入口。')}</section></div>`;
  shell(content);
  drawChart();
}

function drawChart() {
  const canvas = root.querySelector('.chart-canvas');
  if (canvas && state.data) canvas.innerHTML = chartGraphic(rangeRows(state.data.equity,state.range), canvas.clientWidth);
}
window.addEventListener('resize', drawChart);

async function fetchApi(name) {
  try {
    const response = await fetch(`/api/${name}`, { cache: 'no-store', signal: AbortSignal.timeout(8000) });
    const payload = await response.json();
    return { payload, error: response.ok ? null : payload.error || { code: 'API_ERROR', message: '服务返回错误。' } };
  } catch { return { payload: null, error: { code: 'OFFLINE', message: '请确认 Windows 本地 stratided 服务正在运行，然后重新连接。' } }; }
}

async function load() {
  state.loading = true; state.error = null; render();
  const names = ['account','equity','positions','strategies','fills','orders','health','research'];
  const responses = await Promise.all(names.map(fetchApi));
  const result = Object.fromEntries(names.map((n,i)=>[n,responses[i]]));
  state.online = result.health.payload?.data?.service === 'online';
  state.error = names.slice(0,6).map(n=>result[n].error).find(Boolean) || null;
  state.meta = state.error ? null : result.account.payload.snapshot;
  if (!state.error && names.slice(0,6).some(n => result[n].payload.snapshot.snapshot_id !== state.meta.snapshot_id)) {
    state.error = { code:'SNAPSHOT_CHANGED', message:'服务在读取期间重启，收到不同快照。请重新连接。' }; state.meta = null;
  }
  state.data = state.error ? null : Object.fromEntries(names.slice(0,6).map(n=>[n,result[n].payload.data]));
  state.research = result.research.payload?.data; state.researchError = result.research.error;
  state.loading = false; render();
}

function openDetail(kind, index) {
  const row = state.data?.[kind]?.[Number(index)];
  if (!row) return;
  const strategy = kind === 'strategies';
  const deployment = row.deployment;
  drawer.innerHTML = `<div class="drawer-heading"><div><span class="eyebrow">${strategy ? '报表策略' : '持仓详情'}</span><h2 id="drawer-title">${esc(strategy ? deployment.strategy_id : instrument(row.instrument))}</h2></div><button class="icon-button" data-action="close" aria-label="关闭详情">×</button></div><div class="drawer-body">${badge('只读快照', 'mode')}<dl class="metadata"><dt>源日期</dt><dd>${day(state.meta.last_day)}</dd><dt>所属组</dt><dd>${esc(deployment.group_id)}</dd><dt>策略</dt><dd>${esc(deployment.strategy_id)}</dd><dt>冻结版本</dt><dd class="code">${esc(deployment.frozen_version)}</dd><dt>部署标识</dt><dd class="code">${esc(deployment.deployment_id)}</dd>
    ${strategy ? '<dt>运行状态</dt><dd>未接入；仅保留报表记录</dd><dt>独立策略收益 / 回撤</dt><dd>不可用 · 无可信归因指标</dd>' : `<dt>持有 / 可卖</dt><dd class="numeric">${shares(row.quantity)} / ${shares(row.sellable_shares)} 股</dd><dt>未交收 / 预留卖出</dt><dd class="numeric">${shares(row.unsettled_shares)} / ${shares(row.reserved_sell_shares)} 股</dd><dt>持仓市值</dt><dd class="numeric">${money(row.market_value_fen)}</dd><dt>剩余成本</dt><dd class="numeric">${money(row.cost_basis_fen)}</dd><dt>浮动盈亏</dt><dd>${signed(row.unrealized_pnl_fen)}</dd>`}</dl>
    ${strategy ? `<h3>报表中的相关订单</h3><p>${state.data.orders.length} 笔模拟订单，${state.data.fills.length} 笔已确认模拟成交。</p><a class="text-button" href="#history/orders" data-action="close">查看完整订单 →</a>` : `<h3>持仓行情</h3>${empty('行情序列不可用', row.price_series_reason)}<h3>持仓批次</h3>${row.lots.map(l=>`<div class="lot-row"><span>${day(l.acquired_on)}</span><strong class="numeric">${shares(l.quantity)} 股</strong></div>`).join('')}<h3>关联模拟成交</h3><p>${state.data.fills.filter(f=>f.instrument.code === row.instrument.code).length} 笔已确认记录</p><a class="text-button" href="#history/fills" data-action="close">查看交易记录 →</a>`}</div>`;
  drawer.showModal();
}

document.addEventListener('click', event => {
  const target = event.target.closest('[data-action]');
  if (!target || target.disabled) return;
  const { action, value, kind, key, index } = target.dataset;
  if (action === 'reload') { load(); return; }
  if (action === 'close') { drawer.close(); return; }
  if (action === 'detail') { openDetail(kind,index); return; }
  if (action === 'theme') { state.theme = value; remember('theme',value); applyTheme(); }
  if (action === 'metric' || action === 'range') { state[action] = value; remember(action,value); }
  if (action === 'expand') state.expanded[kind] = !state.expanded[kind];
  if (action === 'sort') { const [old,direction] = state.sort[kind].split(':'); state.sort[kind] = `${key}:${old === key && direction === 'asc' ? 'desc' : 'asc'}`; remember(`sort.${kind}`,state.sort[kind]); }
  render();
});
document.addEventListener('keydown', event => {
  if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('tr[data-action="detail"]')) { event.preventDefault(); openDetail(event.target.dataset.kind,event.target.dataset.index); }
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-theme-select]')) { state.theme = event.target.value; remember('theme',state.theme); applyTheme(); render(); }
});
window.addEventListener('hashchange', () => { if (drawer.open) drawer.close(); render(); });
initAgents({ render, drawer });
load();
