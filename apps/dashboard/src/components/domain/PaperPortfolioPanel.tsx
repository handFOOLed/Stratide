import { Card, CardBody, CardHead } from '../ui/Card';
import { TechnicalDetails } from './WorkspaceStudies';
import { formatCny, formatDay } from '../../lib/format';
import type { Order, PaperPortfolio } from '../../lib/types';

export function PaperPortfolioPanel({portfolio, orders}: {portfolio:PaperPortfolio|null; orders:Order[]}) {
  if (portfolio === null) return null;
  return <Card><CardHead title="多证券共享 Paper · 冻结与结算"/><CardBody>
    <p>{portfolio.automatic ? '新意图已启用' : 'Owner 已暂停新意图'} · 固定目标 {formatCny(portfolio.target_value_fen)}/证券 · 最多 {portfolio.max_positions} 只持仓 · 每日最多 {portfolio.max_daily_orders} 笔。</p>
    <p className="muted">仅 Paper 假设模拟。日线开盘在盘后实收后按已冻结顺序记账；真实开盘、历史 PIT 和可交易性均未核验。模型权重不授予交易权限。</p>
    {portfolio.batches.map(b => <section className="study-row" key={b.decision_day}>
      <h3 className="card__title">{formatDay(b.decision_day)} 决策 → {formatDay(b.target_day)} 目标交易日</h3>
      <p>{b.finalized_at === null ? '批次已冻结，等待目标日盘后来源或截止' : '批次已终结'} · {b.candidate === null ? '研究未就绪' : '原候选任务 #'+b.candidate.task_id} · {b.order_ids.length} 笔审批 · {b.rejections.length} 项编译拒绝</p>
      <p className="muted">{b.reason}</p>
      {b.order_ids.map(id => {
        const order = orders.find(o => o.order_id === id);
        if (order === undefined) return <p key={id}>原订单 {id}：未取得账本投影</p>;
        return <p key={id}>{order.instrument.code} · {order.side === 'Buy' ? '买入' : '卖出'} {order.quantity} 股 · 已模拟确认 {order.confirmed_filled_shares} 股 · {order.status} · {order.reason}</p>;
      })}
      {b.rejections.map(([i,reason])=><p key={i.market+i.code}>{i.code} · 未提交 · {reason}</p>)}
      <TechnicalDetails value={b}/>
    </section>)}
    {portfolio.batches.length === 0 ? <p>尚无冻结批次。暖机不足 84 个 READY 会话或缺少原研究证据时保持空仓，原 EOD 继续采集。</p> : null}
    <TechnicalDetails value={{policy_version:portfolio.policy_version,policy_sha256:portfolio.policy_sha256}}/>
  </CardBody></Card>;
}
