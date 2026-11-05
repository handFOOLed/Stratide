// Hierarchy: automation and its current block first; independent egress scope
// second; receipts/details third. Save configuration is the primary action.
// Reuse Card/field/settings-row/btn tokens, existing light/dark themes and type.
import { useEffect, useState } from 'react';
import { agentFetch, friendlyError } from '../../lib/api';
import { formatMicro } from '../../lib/format';
import { Button } from '../ui/Button';
import { Switch } from '../ui/Switch';

interface Config {
  automatic_timesfm: boolean;
  automatic_deepseek: boolean;
  candidate_count: number;
  daily_call_limit: number;
  trading_day_call_limit: number;
  model_version: string;
}
interface Scope {
  provider: string; recipient: string; purpose: string; source_category: string;
  fields: string[]; max_symbols: number; horizon: number; context_sessions: number; valid_until: string;
  provider_terms_reviewed: boolean;
}
interface Run {
  source_day: string; state: string; reason: string | null; cloud_status: string | null;
  events: string[]; universe_count: number | null; qualified_count: number | null;
  selected: Array<{ instrument: string }> | null;
  rejection_counts: Record<string, number> | null;
  candidate_sha256: string | null; fusion_task_id: string | null;
  research: Record<string, unknown> | null;
}
interface Status {
  config: Config; grant: { version: number; authorized_at: string; scope: Scope } | null;
  grant_active: boolean; grant_sha256: string | null; model_installed: boolean;
  fields: string[]; recipient: string; purpose: string; source_category: string; runs: Run[];
  budget: { currency: string; daily_remaining_micro: string; monthly_remaining_micro: string; held_micro: string };
}
const FIELD_LABELS: Record<string, string> = {
  symbols: '最多 8 个证券代码', risk_forecasts: 'TimesFM 5/20 会话 RMS 波动预测',
  baselines: 'Naive / EWMA 基线', source_refs: '来源与模型结果 SHA 引用',
  quality: 'PIT、公司行为和不确定性标签', as_of: '研究决策时间', output_contract: '冻结版本、资产/现金权重与研究输出契约',
};

export function MarketResearchPanel({ token }: { token: string | null }) {
  return token === null ? <p>请先在 Agent 页面解锁本机控制，再配置自动研究与外发许可。</p>
    : <UnlockedMarketResearch key={token} token={token} />;
}

function UnlockedMarketResearch({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState('');
  const [source, setSource] = useState('');
  const [purpose, setPurpose] = useState('');
  const [fields, setFields] = useState<string[]>([]);
  const [maxSymbols, setMaxSymbols] = useState(8);
  const [expires, setExpires] = useState('');
  const [terms, setTerms] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<unknown>(null);
  useEffect(() => {
    const controller = new AbortController();
    agentFetch<Status>(token, 'market-research', { signal: controller.signal })
      .then(v => { setStatus(v); setConfig(v.config); })
      .catch(e => { const failure = friendlyError(e); if (failure.code !== 'ABORTED') setError(failure.message); });
    return () => controller.abort();
  }, [token]);

  async function action(name: string, body: unknown) {
    setBusy(true); setError(null);
    try {
      await agentFetch<unknown>(token, 'market-research/' + name, { method: 'POST', body });
      const v = await agentFetch<Status>(token, 'market-research');
      setStatus(v); setConfig(v.config); setConfirmed(false);
    } catch (e) { setError(friendlyError(e).message); }
    finally { setBusy(false); }
  }
  async function readPreview(day: string) {
    setBusy(true); setError(null);
    try { setPreview(await agentFetch<unknown>(token, 'market-research/preview?day=' + day)); }
    catch (e) { setError(friendlyError(e).message); }
    finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError(null);
    try { const v = await agentFetch<Status>(token, 'market-research'); setStatus(v); setConfig(v.config); }
    catch (e) { setError(friendlyError(e).message); }
    finally { setBusy(false); }
  }
  if (status === null || config === null) return <div role="status">{error === null ? '正在读取本机研究设置…' : error}</div>;
  const current = config;
  const grantReady = provider === 'deepseek' && source === status.source_category && purpose === status.purpose
    && fields.length === status.fields.length && expires !== '' && terms && confirmed;
  return <div className="market-research-settings">
    <h2 className="card__title">全市场自动研究</h2>
    <p>可信盘后快照 → 确定性筛选 → 限量本地 TimesFM CPU → DeepSeek 策略假说。候选仅供研究，PIT 未验证，不创建买卖单。</p>
    {error !== null && <p role="alert">{error}</p>}
    <div className="settings-row"><span>自动 TimesFM CPU</span><Switch label="自动 TimesFM CPU" checked={current.automatic_timesfm}
      onChange={v => setConfig({ ...current, automatic_timesfm: v })} /></div>
    <div className="settings-row"><span>自动 DeepSeek 策略研究</span><Switch label="自动 DeepSeek 策略研究" checked={current.automatic_deepseek}
      onChange={v => setConfig({ ...current, automatic_deepseek: v })} /></div>
    <form onSubmit={e => { e.preventDefault(); void action('configure', current); }}>
      <div className="market-research-fields">
        <label className="field"><span className="field__label">每批候选数（1–8）</span><input className="input" type="number" min="1" max="8" required value={current.candidate_count}
          onChange={e => setConfig({ ...current, candidate_count: Number(e.target.value) })} /></label>
        <label className="field"><span className="field__label">每日云调用上限（上海时区）</span><input className="input" type="number" min="1" max="8" required value={current.daily_call_limit}
          onChange={e => setConfig({ ...current, daily_call_limit: Number(e.target.value) })} /></label>
        <label className="field"><span className="field__label">每源交易日云调用上限</span><input className="input" type="number" min="1" max="8" required value={current.trading_day_call_limit}
          onChange={e => setConfig({ ...current, trading_day_call_limit: Number(e.target.value) })} /></label>
      </div>
      <p className="muted">固定模型：{current.model_version}。Provider 别名可能更新；调用收据保存模型配置指纹。每个源交易日最多一个冻结批次，未知结果不自动重发。</p>
      <div className="market-research-actions"><Button type="submit" variant="primary" disabled={busy}>保存研究配置</Button>
        <Button disabled={busy} onClick={() => void action('pause', {})}>暂停自动研究</Button>
        <Button disabled={busy} onClick={() => void refresh()}>只读刷新</Button>
        {!status.model_installed && <Button disabled={busy} onClick={() => void action('install-model', {})}>复用本机 Provider 配置</Button>}</div>
    </form>
    <h3 className="card__title">共享预算</h3>
    <p>上限 ¥5 / 日、¥100 / 月；使用原 Agent Budget Gate，不可在此加额。未知账单保留最坏预留。</p>
    <p>日剩余 {formatMicro(status.budget.daily_remaining_micro, { currency: status.budget.currency })} · 月剩余 {formatMicro(status.budget.monthly_remaining_micro, { currency: status.budget.currency })}</p>
    <h3 className="card__title">真实数据外发许可 · 独立于自动研究开关</h3>
    <p role="status">{status.grant_active ? '许可有效，仅允许已选字段与范围' : '未获有效许可 · REAL_MARKET_DATA_EGRESS_DENIED'}</p>
    {status.grant !== null && <p>版本 {status.grant.version} · 到期 {status.grant.scope.valid_until}<br /><span className="code-chip code-chip--block">{status.grant_sha256}</span></p>}
    <Button disabled={busy || status.grant === null} onClick={() => void action('revoke', {})}>撤销未来外发</Button>
    <p>撤销会阻止未来调用；不能撤回已发送请求，也不保证接收方删除已有记录。</p>
    <form onSubmit={e => { e.preventDefault(); void action('grant', { confirmed, scope: {
      provider, recipient: status.recipient, purpose, source_category: source, fields,
      max_symbols: maxSymbols, horizon: 20, context_sessions: 84, valid_until: new Date(expires).toISOString(), provider_terms_reviewed: terms,
    } }); }}>
      <div className="market-research-fields">
        <label className="field"><span className="field__label">接收方</span><select className="select" required value={provider} onChange={e => { setProvider(e.target.value); setConfirmed(false); }}>
          <option value="">请选择</option><option value="deepseek">DeepSeek · api.deepseek.com/chat/completions</option></select></label>
        <label className="field"><span className="field__label">来源</span><select className="select" required value={source} onChange={e => { setSource(e.target.value); setConfirmed(false); }}>
          <option value="">请选择</option><option value={status.source_category}>Tushare 可信 EOD 派生研究摘要</option></select></label>
        <label className="field"><span className="field__label">用途</span><select className="select" required value={purpose} onChange={e => { setPurpose(e.target.value); setConfirmed(false); }}>
          <option value="">请选择</option><option value={status.purpose}>市场策略与定量组合假说研究</option></select></label>
        <label className="field"><span className="field__label">最大证券数</span><input className="input" type="number" required min="1" max="8" value={maxSymbols}
          onChange={e => { setMaxSymbols(Number(e.target.value)); setConfirmed(false); }} /></label>
        <label className="field"><span className="field__label">许可到期（本机时间）</span><input className="input" type="datetime-local" required value={expires}
          onChange={e => { setExpires(e.target.value); setConfirmed(false); }} /></label>
      </div>
      <fieldset className="market-research-checks"><legend>逐项允许外发的字段（本协议需全部选择）</legend>
        {status.fields.map(field => <label key={field}><input type="checkbox" checked={fields.includes(field)} onChange={e => {
          setFields(e.target.checked ? [...fields, field] : fields.filter(f => f !== field)); setConfirmed(false);
        }} />{FIELD_LABELS[field]}</label>)}
      </fieldset>
      <p>范围：当前批次最多 {maxSymbols} 个候选、84 个会话的派生风险摘要、20 会话预测。账户余额、真实持仓、账本、密钥与原始行情文件持续禁止外发。</p>
      <label className="market-research-check"><input type="checkbox" checked={terms} onChange={e => { setTerms(e.target.checked); setConfirmed(false); }} />
        我已核对 <a href="https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html" target="_blank" rel="noreferrer">DeepSeek 接收与保留条款</a>及 Tushare 来源许可，确认本范围可发送。</label>
      <label className="market-research-check"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我明确授权上述接收方、用途、来源、字段、范围和期限。</label>
      <Button type="submit" disabled={busy || !grantReady}>确认并保存外发许可</Button>
    </form>
    <h3 className="card__title">任务进度与冻结候选</h3>
    {status.runs.length === 0 && <p>暂无批次；等待可信全市场快照 READY 与自动研究配置。</p>}
    {status.runs.map(run => <div className="market-research-run" key={run.source_day}>
      <strong>{run.source_day} · {run.state}</strong><p>{run.events.join(' → ')}</p>
      <p>全证券池 {run.universe_count === null ? '待筛选' : run.universe_count} · 合格 {run.qualified_count === null ? '待筛选' : run.qualified_count}
        {' · '}{run.reason === null ? '无拒绝' : run.reason}</p>
      {run.selected !== null && <p>候选：{run.selected.map(s => s.instrument).join('、')}</p>}
      {run.rejection_counts !== null && <details className="disclosure"><summary>筛选拒绝原因</summary><pre>{JSON.stringify(run.rejection_counts, null, 2)}</pre></details>}
      <p>未验证假说 · RESEARCH_ONLY · PIT 未验证</p>
      {run.research !== null && <details className="disclosure"><summary>冻结资产/现金权重、未验证策略假说与调用收据</summary><pre className="market-research-preview">{JSON.stringify(run.research, null, 2)}</pre></details>}
      {run.candidate_sha256 !== null && <p className="code-chip code-chip--block">候选版本 {run.candidate_sha256}</p>}
      <Button disabled={busy} onClick={() => void readPreview(run.source_day)}>预览待发 payload 与最坏费用</Button>
    </div>)}
    {preview !== null && <details open className="disclosure"><summary>本机 payload 预览 · 未发送</summary><pre className="market-research-preview">{JSON.stringify(preview, null, 2)}</pre></details>}
  </div>;
}
