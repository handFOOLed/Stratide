import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { StatusBadge } from '../ui/StatusBadge';
import { formatBps, formatCny, formatDay, parseInteger } from '../../lib/format';
import { humanReasonText, statusView } from '../../lib/status';
import type { StatusView } from '../../lib/status';
import type { EquityRow } from '../../lib/types';
import { DrawerSection } from './DrawerSection';

function moneyText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatCny(value);
}

function signedMoneyText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatCny(value, { signed: true });
}

function returnText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatBps(value, { signed: true });
}

function missingValueStatus(reason: string): StatusView {
  const human = humanReasonText(reason);
  return human === null ? statusView('attention', '数据缺失') : statusView('attention', '数据缺失', human);
}

export function DayDrawer({
  row,
  previous,
  open,
  onClose,
}: {
  row: EquityRow | null;
  previous: EquityRow | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!row) return null;
  const nav = parseInteger(row.nav_fen);
  const cash = parseInteger(row.cash_fen);
  const holdings = nav !== null && cash !== null ? (nav - cash).toString() : null;
  const previousNav = previous === null ? null : parseInteger(previous.nav_fen);
  const change = nav !== null && previousNav !== null ? (nav - previousNav).toString() : null;
  const valuation = row.valuation_error === null ? statusView('ok', '数据正常') : missingValueStatus(row.valuation_error);
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="每日账本"
      title={formatDay(row.day)}
      meta={<StatusBadge status={valuation} size="sm" />}
    >
      <div data-testid="day-drawer">
        {row.valuation_error === null ? null : (
          <Callout tone="warning" className="drawer-callout">
            这天的估值数据不完整，缺失的数字保持空白。
          </Callout>
        )}

        <DrawerSection title="当日账户">
          <Kv
            items={[
              { label: '账户资产', value: moneyText(row.nav_fen) },
              { label: '现金', value: moneyText(row.cash_fen) },
              { label: '持仓市值', value: holdings === null ? '未记录' : formatCny(holdings) },
              { label: '累计盈亏', value: signedMoneyText(row.cumulative_pnl_fen) },
              { label: '累计收益率', value: returnText(row.return_bps) },
              { label: '较上一数据日', value: change === null ? '未记录' : formatCny(change, { signed: true }) },
            ]}
          />
          <p className="drawer-note">持仓市值 = 账户资产 − 现金。</p>
          <p className="drawer-note">较上一数据日只比较账面资产，未扣除资金转入转出。</p>
        </DrawerSection>

        <div className="drawer-diagnostics">
          <Diagnostics
            title="账本诊断信息"
            items={[
              { label: '数据日期', value: formatDay(row.day) },
              { label: '估值状态（原始值）', value: row.valuation_error ?? '无错误' },
              { label: '账户资产（原始值）', value: row.nav_fen ?? '未记录' },
              { label: '现金（原始值）', value: row.cash_fen ?? '未记录' },
              { label: '累计盈亏（原始值）', value: row.cumulative_pnl_fen ?? '未记录' },
              { label: '累计收益率（原始值）', value: row.return_bps ?? '未记录' },
            ]}
            data={{ row, previous }}
          />
        </div>
      </div>
    </Drawer>
  );
}
