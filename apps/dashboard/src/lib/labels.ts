import type { BadgeTone } from '../components/ui/Badge';

export const MODE_LABELS: Record<string, { label: string; tone: BadgeTone; description: string }> = {
  synthetic_test: {
    label: '合成测试',
    tone: 'warning',
    description: '仓库合成测试报告，仅验证软件行为，不代表真实市场结果。',
  },
  historical_replay: {
    label: '历史回放',
    tone: 'accent',
    description: '历史 EOD 模拟结果；历史可用时间未获独立 point-in-time 核验。',
  },
  forward_paper: {
    label: '前向模拟',
    tone: 'accent',
    description: '真实前向 Paper 账户记录，不是券商成交或实盘收益。',
  },
};

export const EVIDENCE_LABELS: Record<string, string> = {
  engine_test_only: '引擎测试证据',
  exploratory_not_verified: '探索性 · PIT 未核验',
  independent_verified: '独立核验证据',
  exploratory: '探索性证据',
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '研究中',
  completed: '已完成',
  failed: '失败',
  cancel_requested: '已申请取消',
  cancelled: '已取消',
  outcome_uncertain: '结果 / 费用不确定',
  skipped: '已跳过',
};

export const TASK_STATUS_TONES: Record<string, BadgeTone> = {
  queued: 'neutral',
  running: 'accent',
  completed: 'success',
  failed: 'danger',
  cancel_requested: 'warning',
  cancelled: 'neutral',
  outcome_uncertain: 'warning',
  skipped: 'neutral',
};

export const ORDER_STATUS_TONES: Record<string, BadgeTone> = {
  Open: 'neutral',
  PartiallyFilled: 'accent',
  Filled: 'success',
  Rejected: 'danger',
  Expired: 'warning',
};

export const EOD_DISPOSITION_LABELS: Record<string, string> = {
  queued: '已入队',
  running: '研究中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  outcome_uncertain: '结果 / 费用不确定',
  skipped: '已跳过',
  not_triggered: '尚未触发',
};

export const AVAILABILITY_LABELS: Record<string, string> = {
  not_verified: '未验证',
  available: '可用',
  unavailable: '不可用',
  unavailable_or_outcome_unknown: '状态未知，可能含未结费用',
};

export const AVAILABILITY_TONES: Record<string, BadgeTone> = {
  not_verified: 'neutral',
  available: 'success',
  unavailable: 'warning',
  unavailable_or_outcome_unknown: 'warning',
};

export const VERIFICATION_LABELS: Record<string, string> = {
  FAKE_SYNTHETIC_ONLY: 'FAKE / SYNTHETIC',
  REAL_PROVIDER_NOT_VERIFIED: 'REAL_PROVIDER_NOT_VERIFIED',
  VERIFIED: '已核验',
};

export const RESEARCH_QUALIFICATION_LABELS: Record<string, string> = {
  EXPLORATORY_NOT_INDEPENDENT: '探索性 · 非独立资格',
};

export const BUDGET_STATE_LABELS: Record<string, string> = {
  configured: '已配置',
  unconfigured: '未配置',
};

export function modeInfo(mode: string | null | undefined) {
  if (!mode) return { label: '未知模式', tone: 'neutral' as BadgeTone, description: '服务未提供快照模式。' };
  return MODE_LABELS[mode] ?? { label: mode, tone: 'neutral' as BadgeTone, description: '未识别的快照模式，保留原始值。' };
}
