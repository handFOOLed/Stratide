import { Badge } from '../ui/Badge';
import type { BadgeTone } from '../ui/Badge';
import {
  AVAILABILITY_LABELS,
  AVAILABILITY_TONES,
  EVIDENCE_LABELS,
  MODE_LABELS,
  ORDER_STATUS_TONES,
  TASK_STATUS_LABELS,
  TASK_STATUS_TONES,
} from '../../lib/labels';
import type { SnapshotMeta } from '../../lib/types';

export function ModeBadge({ mode }: { mode: string | null | undefined }) {
  const info = mode ? MODE_LABELS[mode] : undefined;
  return (
    <Badge tone={info?.tone ?? 'neutral'} title={info?.description}>
      {info?.label ?? '未知模式（见技术详情）'}
    </Badge>
  );
}

export function EvidenceBadge({ evidence }: { evidence: string | null | undefined }) {
  if (!evidence) return <Badge tone="neutral">证据未知</Badge>;
  return <Badge tone={evidence === 'engine_test_only' ? 'warning' : 'neutral'}>{EVIDENCE_LABELS[evidence] ?? '证据待核对'}</Badge>;
}

export function SideBadge({ side }: { side: string }) {
  return (
    <Badge tone={side === 'Buy' ? 'gain' : side === 'Sell' ? 'loss' : 'neutral'}>
      {side === 'Buy' ? '买入' : side === 'Sell' ? '卖出' : side}
    </Badge>
  );
}

export function OrderStatusBadge({ status, label }: { status: string; label: string }) {
  return <Badge tone={ORDER_STATUS_TONES[status] ?? 'neutral'}>{label}</Badge>;
}

export function TaskStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={TASK_STATUS_TONES[status] ?? 'neutral'} title={status}>
      {TASK_STATUS_LABELS[status] ?? '状态待核对'}
    </Badge>
  );
}

export function AvailabilityBadge({ availability }: { availability: string }) {
  return (
    <Badge tone={AVAILABILITY_TONES[availability] ?? 'neutral'} title={availability}>
      {AVAILABILITY_LABELS[availability] ?? '状态待核对'}
    </Badge>
  );
}

export function SnapshotBadges({ meta }: { meta: SnapshotMeta | null }) {
  if (!meta) return null;
  return (
    <>
      <ModeBadge mode={meta.mode} />
      <Badge tone="outline">源日 {meta.last_day ? meta.last_day.slice(0, 4) + '-' + meta.last_day.slice(4, 6) + '-' + meta.last_day.slice(6, 8) : '—'}</Badge>
      <Badge tone="outline">仅快照 · 非实时</Badge>
    </>
  );
}

export function toneForBoolean(ok: boolean): BadgeTone {
  return ok ? 'success' : 'warning';
}
