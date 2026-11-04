/* Hierarchy: saved research -> evidence class -> technical provenance. One
   refresh action; existing surface/type/space tokens, no decorative imagery. §2.1 */
import { Card, CardBody, CardHead } from '../ui/Card';
import { Button } from '../ui/Button';
import { ModeBadge } from './Badges';
import { stateLabel } from '../../lib/workspace';
import type { WorkspaceState } from '../../lib/workspace';
import { formatBps,formatDateTime } from '../../lib/format';

export function TechnicalDetails({value}: {value: unknown}) {
  return <details className="technical-details"><summary>技术详情与完整来源</summary><pre tabIndex={0}>{JSON.stringify(value, null, 2)}</pre><Button size="sm" variant="ghost" onClick={() => void navigator.clipboard.writeText(JSON.stringify(value,null,2))}>复制详情</Button></details>;
}
export function WorkspaceStudies({workspace}: {workspace: WorkspaceState}) {
  const data = workspace.data;
  return <Card className="workspace-studies"><CardHead title="本地研究与样本外报告" actions={<Button variant="ghost" size="sm" onClick={workspace.refresh}>读取资料</Button>}/><CardBody>
    <p className="muted">研究保留原任务与来源；历史和合成结果均不计入当前 Paper 账户。</p>
    {workspace.error ? <div role="alert">{workspace.error.message}<TechnicalDetails value={{code:workspace.error.code}}/></div> : null}
    {data === null ? <p>正在读取本地资料。</p> : <>
      {data.market === undefined ? null : <section className="study-row" aria-label="全市场 EOD 采集">
        <h3 className="card__title">全市场 EOD 采集</h3>
        {data.market.data_mode === undefined ? null : <ModeBadge mode={data.market.data_mode}/>}
        <p>采集状态：{data.market.state === 'READY' ? '数据覆盖合格' : data.market.state === 'NOT_CONFIGURED' ? '未配置' : data.market.state === 'MARKET_CLOSED' ? '交易所休市' : '等待或受阻（见详情）'} · 最后成功日期：{data.market.last_successful_date === null ? '尚无' : data.market.last_successful_date}</p>
        {data.market.latest === null ? null : <>
          <p>源日 {data.market.latest.source_day} · 全市场有行情 {data.market.latest.actual_quoted}/{data.market.latest.expected_market}；行情与已确认全天停牌合计 {data.market.latest.market_explained}/{data.market.latest.expected_market}（{(data.market.latest.market_coverage_bps / 100).toFixed(2)}%）</p>
          <p>研究选样合格 {data.market.latest.eligible_count}/{data.market.latest.research_denominator} · 实际可用时间 {formatDateTime(data.market.latest.available_at)}</p>
        </>}
        <p className="muted">缺口日期 {data.market.gaps.length}；BSE 保留覆盖记录，尚不支持研究准入。读取资料只查询本地数据。</p>
        <TechnicalDetails value={data.market}/>
      </section>}
      {data.studies.length === 0 && data.evaluations.length === 0 ? <p className="compact-empty">尚无已配置研究资料；在本机启动配置中选择原研究批次和报告。</p> : null}
      {data.studies.map(s => <article className="study-row" key={s.id}><div className="study-row__title"><strong>{s.kind} · {s.name}</strong><span>{stateLabel(s.state)}</span></div>
        {s.mode ? <ModeBadge mode={s.mode}/> : null} {s.task_id ? <span>原任务 #{s.task_id}</span> : null}
        <p className="muted">{s.billing ? stateLabel(s.billing) : '来源核对受阻'} · 仅供研究</p>
        {s.received_at===undefined?null:<p className="muted">{s.mode==='historical_research_only'?'输入最近实际取得时间':'合成输入时点'}：{formatDateTime(s.received_at)}</p>}
        {s.risk_rows===undefined?null:s.risk_rows.map(r=><div className="study-row" key={r.instrument}><strong>{r.instrument}</strong><p>截止 {formatDateTime(r.as_of)} · 未校准的日风险代理</p><div className="inline-row">{r.forecasts.map(f=><span key={f.sessions}>{f.sessions} 会话 RMS {(f.value_ratio*100).toFixed(4)}%</span>)}<span>Naive {(r.naive*100).toFixed(4)}%</span><span>EWMA {(r.ewma*100).toFixed(4)}%</span></div><p className="muted">方向未知；这些数值不是预期收益或 VaR。</p></div>)}
        {s.portfolio===undefined||s.portfolio===null?null:<div><p>研究现金权重 {formatBps(String(s.portfolio.cash_weight_bps))}</p>{s.portfolio.positions.map(p=><p key={p.instrument}>{p.instrument} · 研究权重 {formatBps(String(p.weight_bps))}</p>)}<p className="muted">合成组合假设，不是当前持仓或交易许可。</p></div>}
        <TechnicalDetails value={s}/></article>)}
      {data.evaluations.map(e => <article className="study-row" key={e.id}><strong>样本外评价 · {e.name}</strong><p>{stateLabel(e.state)}；{e.verdict==='STRUCTURALLY_UNREACHABLE'?'当前协议样本量达不到预设门槛。':'证据不足以授予交易资格。'}</p>
        {e.split_rows===undefined?null:e.split_rows.map(split=><div key={split.name}><p>{split.name==='development'?'开发段':split.name==='validation'?'验证段':'测试段'}：{split.scored}/{split.samples} 样本计分，覆盖 {(split.coverage*100).toFixed(1)}%</p><div className="mini-table-wrap"><table className="mini-table"><caption className="sr-only">日风险代理误差，收益率比值单位</caption><thead><tr><th>模型</th><th>会话</th><th className="num">MAE</th><th className="num">RMSE</th></tr></thead><tbody>{split.metrics.map(m=><tr key={m.model+m.horizon}><td>{m.model==='timesfm'?'TimesFM':m.model==='naive'?'Naive':'EWMA'}</td><td>{m.horizon}</td><td className="num">{m.mae.toFixed(6)}</td><td className="num">{m.rmse.toFixed(6)}</td></tr>)}</tbody></table></div></div>)}
        <TechnicalDetails value={e}/></article>)}
      {data.candidates.length===0?null:<section className="study-row"><h3 className="card__title">原 Registry 候选</h3><p className="muted">保留原来源与版本；登记或冻结不等于独立评价通过或交易许可。</p>{data.candidates.map((c,i)=><article className="study-row" key={c.registry+String(i)}><strong>{c.registry} · {stateLabel(c.state)}</strong>{c.mode===undefined?null:<ModeBadge mode={c.mode}/>}<p>{c.task_id===undefined?'原本地登记记录':'原任务 #'+c.task_id}{c.registered_at===undefined?'':' · '+formatDateTime(c.registered_at)}</p><TechnicalDetails value={c}/></article>)}</section>}
    </>}
  </CardBody></Card>;
}
