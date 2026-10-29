import { Badge } from '../ui/Badge';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import {
  formatCny,
  formatDay,
  formatShares,
  instrumentLabel,
  sideLabel,
} from '../../lib/format';
import type { Fill, Position } from '../../lib/types';
import { DrawerNote, DrawerSection } from './DrawerSection';
import { ModeBadge, SideBadge } from './Badges';
import type { SnapshotMeta } from '../../lib/types';

export function PositionDrawer({
  position,
  open,
  fills,
  meta,
  onClose,
}: {
  position: Position | null;
  open: boolean;
  fills: Fill[];
  meta: SnapshotMeta | null;
  onClose: () => void;
}) {
  if (!position) return null;
  const related = fills.filter((fill) => fill.instrument.code === position.instrument.code);
  const lots = position.lots ?? [];
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="持仓详情"
      title={instrumentLabel(position.instrument)}
      meta={
        <>
          <Badge tone="outline">{position.instrument.market}</Badge>
          <Badge tone="neutral">{formatDay(meta?.last_day ?? null)}</Badge>
          {meta ? <ModeBadge mode={meta.mode} /> : null}
        </>
      }
    >
      <DrawerSection title="持仓">
        <Kv
          items={[
            { label: '持有数量', value: formatShares(position.quantity) + ' 股' },
            { label: '可卖数量', value: formatShares(position.sellable_shares) + ' 股' },
            { label: '未交收', value: formatShares(position.unsettled_shares) + ' 股' },
            { label: '预留卖出', value: formatShares(position.reserved_sell_shares) + ' 股' },
          ]}
        />
      </DrawerSection>

      <DrawerSection title="估值">
        <Kv
          items={[
            { label: '持仓市值', value: formatCny(position.market_value_fen) },
            { label: '剩余成本', value: formatCny(position.cost_basis_fen) },
            { label: '浮动盈亏', value: formatCny(position.unrealized_pnl_fen, { signed: true }) },
          ]}
        />
        <DrawerNote>市值只从已核对的有效 NAV 与现金导出；报告没有独立行情序列。</DrawerNote>
      </DrawerSection>

      <DrawerSection title="持仓批次">
        {lots.length === 0 ? (
          <DrawerNote>报告未提供持仓批次。</DrawerNote>
        ) : (
          <div className="mini-table-wrap">
            <table className="mini-table">
              <thead>
                <tr>
                  <th>取得日期</th>
                  <th className="num">数量</th>
                  <th className="num">成本</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot, index) => (
                  <tr key={index}>
                    <td>{formatDay(lot.acquired_on ?? null)}</td>
                    <td className="num">{formatShares(lot.quantity)}</td>
                    <td className="num">{formatCny(lot.cost_basis_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DrawerSection>

      <DrawerSection title="行情序列">
        <p className="prose">{position.price_series_reason || '报告没有提供可用的行情序列。'}</p>
        <DrawerNote>页面不会用其他日期或外部行情补齐该证券的价格。</DrawerNote>
      </DrawerSection>

      <DrawerSection title={'关联模拟成交 · ' + String(related.length)}>
        {related.length === 0 ? (
          <DrawerNote>当前报告中没有该证券的已确认模拟成交。</DrawerNote>
        ) : (
          <div className="mini-table-wrap">
            <table className="mini-table">
              <thead>
                <tr>
                  <th>日期 / 方向</th>
                  <th className="num">数量</th>
                  <th className="num">价格</th>
                </tr>
              </thead>
              <tbody>
                {related.slice(-5).reverse().map((fill) => (
                  <tr key={fill.fill_id}>
                    <td>
                      {formatDay(fill.day)} <SideBadge side={fill.side} />
                    </td>
                    <td className="num">{formatShares(fill.quantity)}</td>
                    <td className="num">{formatCny(fill.price_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <DrawerNote>仅显示最近最多五笔关联成交，不在此抽屉内复制完整历史表。</DrawerNote>
      </DrawerSection>

      <DrawerSection title="部署记录">
        <Kv
          items={[
            { label: '所属组', value: position.deployment.group_id },
            { label: '策略', value: position.deployment.strategy_id },
            { label: '冻结版本', value: position.deployment.frozen_version },
            { label: '部署标识', value: position.deployment.deployment_id },
          ]}
        />
      </DrawerSection>
    </Drawer>
  );
}