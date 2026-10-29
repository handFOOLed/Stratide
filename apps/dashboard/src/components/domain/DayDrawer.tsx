import { Badge } from '../ui/Badge';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { parseInteger } from '../../lib/format';
import { formatBps, formatCny, formatDay } from '../../lib/format';
import type { EquityRow } from '../../lib/types';
import { DrawerNote, DrawerSection } from './DrawerSection';

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
  const previousNav = previous ? parseInteger(previous.nav_fen) : null;
  const change = nav !== null && previousNav !== null ? (nav - previousNav).toString() : null;
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="逐日核对"
      title={formatDay(row.day)}
      meta={<Badge tone={row.valuation_error ? 'warning' : 'success'}>{row.valuation_error ? '估值缺失' : '有效估值'}</Badge>}
    >
      <DrawerSection title="当日账户">
        <Kv
          items={[
            { label: '账户净值', value: formatCny(row.nav_fen) },
            { label: '现金', value: formatCny(row.cash_fen) },
            { label: '隐含持仓市值', value: formatCny(holdings) },
            { label: '累计盈亏', value: formatCny(row.cumulative_pnl_fen, { signed: true }) },
            { label: '累计收益率', value: formatBps(row.return_bps, { signed: true }) },
            { label: '较上一源日', value: change === null ? '—' : formatCny(change, { signed: true }) },
            { label: '估值状态', value: row.valuation_error || '有效' },
          ]}
        />
        <DrawerNote>
          隐含持仓市值 = 报告中的 NAV − 现金，仅用于核对六报告内部一致性，不是独立行情估值。
        </DrawerNote>
      </DrawerSection>

      <DrawerSection title="核对口径">
        <p className="prose">
          本页只读取已发布六报告中的逐日字段。当前 API 没有提供逐日外部资金流和逐日费用拆分，因此“较上一源日”不声称已扣除资金流，也不替代完整 TWR。
        </p>
        <DrawerNote>缺失估值保留为 null，不用前后日期插值或零值填补。</DrawerNote>
      </DrawerSection>
    </Drawer>
  );
}
