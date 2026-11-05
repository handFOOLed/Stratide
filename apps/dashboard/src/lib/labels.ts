import type { BadgeTone } from '../components/ui/Badge';

/**
 * 旧版 Badge / 状态文案映射。
 * 新代码请使用 lib/status.ts（统一 5 态）与 components/ui/StatusBadge.tsx。
 * 这里保留的 MODE/EVIDENCE/VERIFICATION 只允许在“诊断信息”折叠区展示。
 */

export const MODE_LABELS: Record<string, { label: string; tone: BadgeTone; description: string }> = {
  tushare_incremental_eod: { label: '盘后行情采集', tone: 'neutral', description: '每日收盘后从 Tushare 拉取的增量行情，非实时。' },
  ex_post_paper_assumption: { label: '模拟成交假设', tone: 'neutral', description: '前一日冻结意图，次日盘后按开盘价模拟成交；不是真实成交。' },
  historical_research_only: { label: '历史研究数据', tone: 'neutral', description: '事后取得的历史数据，仅用于本地研究。' },
  forward_observed_eod: { label: '前向盘后观察', tone: 'neutral', description: '实际时间戳记录的盘后观察，不等于已成交。' },
  synthetic_test: { label: '本地测试数据', tone: 'warning', description: '仓库内合成测试数据，仅验证软件行为，不代表真实市场结果。' },
  historical_replay: { label: '历史回放', tone: 'accent', description: '历史模拟结果；历史时点可用性未获独立核验。' },
  forward_paper: { label: '前向模拟', tone: 'accent', description: '真实前向模拟账户记录，不是券商成交或实盘收益。' },
};

export const EVIDENCE_LABELS: Record<string, string> = {
  EX_POST_OPEN_ASSUMPTION: '次日开盘价模拟成交假设',
  exploratory_historical_replay_not_pit_verified: '历史回放，时点可用性未核验',
  engine_test_only: '引擎测试数据',
  exploratory_not_verified: '探索性，尚未独立核验',
  independent_verified: '独立核验',
  exploratory: '探索性',
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  local_running: '运行中',
  completed: '已完成',
  failed: '运行失败',
  cancel_requested: '正在取消',
  cancelled: '已取消',
  outcome_uncertain: '结果未确认',
  skipped: '已跳过',
  blocked: '已被阻止',
};

export const TASK_STATUS_TONES: Record<string, BadgeTone> = {
  queued: 'neutral',
  running: 'accent',
  completed: 'success',
  failed: 'danger',
  local_running: 'accent',
  cancel_requested: 'warning',
  cancelled: 'neutral',
  outcome_uncertain: 'warning',
  skipped: 'neutral',
  blocked: 'warning',
};

export const ORDER_STATUS_TONES: Record<string, BadgeTone> = {
  Open: 'neutral',
  PartiallyFilled: 'accent',
  Filled: 'success',
  Rejected: 'danger',
  Expired: 'warning',
};

export const EOD_DISPOSITION_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '运行失败',
  cancelled: '已取消',
  outcome_uncertain: '结果未确认',
  skipped: '已跳过',
  skipped_superseded: '已跳过（有更新的数据日）',
  skipped_paused: '已跳过（研究已暂停）',
  not_triggered: '尚未触发',
};

export const AVAILABILITY_LABELS: Record<string, string> = {
  not_verified: '尚未验证',
  available: '正常',
  last_task_completed: '最近调用正常',
  unavailable: '不可用',
  unavailable_or_outcome_unknown: '结果未确认',
};

export const AVAILABILITY_TONES: Record<string, BadgeTone> = {
  not_verified: 'neutral',
  available: 'success',
  last_task_completed: 'success',
  unavailable: 'warning',
  unavailable_or_outcome_unknown: 'warning',
};

/** 诊断用：模型/服务验证状态。 */
export const VERIFICATION_LABELS: Record<string, string> = {
  FAKE_SYNTHETIC_ONLY: '本地测试数据',
  REAL_PROVIDER_NOT_VERIFIED: '真实服务尚未验证',
  REAL_PROVIDER_CALL_OBSERVED: '已有真实调用记录',
  LOCAL_NO_BILLING: '本地运行，不产生费用',
  VERIFIED: '已核验',
};

export const RESEARCH_QUALIFICATION_LABELS: Record<string, string> = {
  EXPLORATORY_NOT_INDEPENDENT: '探索性研究（尚未独立核验）',
};

export const BUDGET_STATE_LABELS: Record<string, string> = {
  configured: '已设置',
  unconfigured: '未设置',
};

export function modeInfo(mode: string | null | undefined) {
  if (!mode) return { label: '数据模式未知', tone: 'neutral' as BadgeTone, description: '服务未提供数据模式。' };
  return MODE_LABELS[mode] ?? { label: '数据模式未知', tone: 'neutral' as BadgeTone, description: '未识别的数据模式，原始值见诊断信息。' };
}
