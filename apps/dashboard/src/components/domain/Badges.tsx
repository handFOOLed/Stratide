import { Badge } from '../ui/Badge';
import type { BadgeTone } from '../ui/Badge';
import { StatusBadge } from '../ui/StatusBadge';
import { availabilityView, orderStatusView, taskStatusView } from '../../lib/status';
import {
  AVAILABILITY_LABELS,
  AVAILABILITY_TONES,
  EVIDENCE_LABELS,
  MODE_LABELS,
} from '../../lib/labels';
import type { SnapshotMeta } from '../../lib/types';

/** 数据模式 / 证据等级只允许出现在“诊断信息”折叠区。 */
export function ModeBadge({ mode }: { mode: string | null | undefined }) {
  const info = mode ? MODE_LABELS[mode] : undefined;
  return (
    <Badge tone={info?.tone ?? 'neutral'} title={info?.description}>
      {info?.label ?? '数据模式未知'}
    </Badge>
  );
}

export function EvidenceBadge({ evidence }: { evidence: string | null | undefined }) {
  if (!evidence) return <Badge tone="neutral">证据等级未知</Badge>;
  return <Badge tone={evidence === 'engine_test_only' ? 'warning' : 'neutral'}>{EVIDENCE_LABELS[evidence] ?? '证据等级未知'}</Badge>;
}

export function SideBadge({ side }: { side: string }) {
  return (
    <Badge tone={side === 'Buy' ? 'gain' : side === 'Sell' ? 'loss' : 'neutral'}>
      {side === 'Buy' ? '买入' : side === 'Sell' ? '卖出' : '方向未知'}
    </Badge>
  );
}

export function OrderStatusBadge({ status, reason = null }: { status: string; reason?: string | null }) {
  return <StatusBadge status={orderStatusView(status, reason)} size="sm" />;
}

export function TaskStatusBadge({
  status,
  reason = null,
  conclusion = null,
}: {
  status: string;
  reason?: string | null;
  conclusion?: string | null;
}) {
  return <StatusBadge status={taskStatusView(status, reason, conclusion)} size="sm" />;
}

export function AvailabilityBadge({ availability }: { availability: string }) {
  return <StatusBadge status={availabilityView(availability)} size="sm" />;
}

export function SnapshotBadges({ meta }: { meta: SnapshotMeta | null }) {
  if (!meta) return null;
  return (
    <>
      <ModeBadge mode={meta.mode} />
      <Badge tone="outline">数据日期 {meta.last_day ? meta.last_day.slice(0, 4) + '-' + meta.last_day.slice(4, 6) + '-' + meta.last_day.slice(6, 8) : '—'}</Badge>
      <Badge tone="outline">仅盘后数据 · 非实时</Badge>
    </>
  );
}

export function toneForBoolean(ok: boolean): BadgeTone {
  return ok ? 'success' : 'warning';
}
