import { Card, CardBody } from '../ui/Card';
import { InfoHint } from '../ui/InfoHint';
import { EmptyState } from '../ui/EmptyState';
import { StatusLine } from '../ui/StatusBadge';
import { countText, formatCny } from '../../lib/format';
import { statusView } from '../../lib/status';
import { TERMS } from '../../lib/copy';
import type { Order, PaperPortfolio } from '../../lib/types';

/**
 * 普通投资者能看懂的模拟交易规则摘要。
 * 批次、冻结、拒绝、容量等内部记录只出现在总览页底部的“诊断信息”里。
 */
export function PaperPortfolioPanel({
  portfolio,
}: {
  portfolio: PaperPortfolio | null;
  orders: Order[];
}) {
  if (portfolio === null) return null;
  const automatic = portfolio.automatic;
  const status = automatic
    ? statusView('ok', '正常', '新的模拟交易计划会自动生成')
    : statusView('attention', '已暂停', '暂停期间不会生成新的模拟交易计划');
  const emptyDescription = automatic
    ? '尚未产生模拟交易批次；数据准备完成后会自动开始。'
    : '尚未产生模拟交易批次；自动生成当前已暂停。';

  return (
    <Card className="portfolio-rules" data-testid="portfolio-rules">
      <CardBody>
        <div className="portfolio-rules__head">
          <div>
            <h2 className="portfolio-rules__title">
              模拟交易规则
              <InfoHint label="模拟交易规则说明">
                系统在收盘后生成计划，下个交易日按开盘价模拟成交；只在本机模拟，不连接券商。
              </InfoHint>
            </h2>
            <p className="portfolio-rules__subtitle">系统按这些规则自动更新模拟交易，不需要你逐笔操作。</p>
          </div>
          <StatusLine status={status} />
        </div>

        <dl className="portfolio-rules__grid">
          <div>
            <dt>单只目标金额</dt>
            <dd className="numeric">{formatCny(portfolio.target_value_fen)}</dd>
          </div>
          <div>
            <dt>最多持仓数量</dt>
            <dd className="numeric">{countText(portfolio.max_positions, '只')}</dd>
          </div>
          <div>
            <dt>每日最多订单数</dt>
            <dd className="numeric">{countText(portfolio.max_daily_orders, '笔')}</dd>
          </div>
          <div>
            <dt>成交方式</dt>
            <dd>{TERMS.simulatedFill}</dd>
          </div>
        </dl>

        {portfolio.batches.length === 0 ? (
          <div className="portfolio-rules__empty">
            <EmptyState compact icon="calendar" title="还没有模拟交易" description={emptyDescription} />
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
