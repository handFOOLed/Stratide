import type { BadgeTone } from '../components/ui/Badge';

export const MODE_LABELS: Record<string, { label: string; tone: BadgeTone; description: string }> = {
  ex_post_paper_assumption: {label:'Paper 假设成交',tone:'warning',description:'前一日冻结意图，次日盘后事后确认；不是开盘实收或真实交易。'},
  historical_research_only: {label:'事后历史研究',tone:'neutral',description:'事后取得的历史输入，仅本地研究。'},
  forward_observed_eod: {label:'前向盘后观察',tone:'neutral',description:'实际时间戳记录的盘后观察，不等于已成交。'},
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
  EX_POST_OPEN_ASSUMPTION: '事后开盘价假设',
  exploratory_historical_replay_not_pit_verified:'事后历史 · PIT 未验证',
  engine_test_only: '引擎测试证据',
  exploratory_not_verified: '探索性 · PIT 未核验',
  independent_verified: '独立核验证据',
  exploratory: '探索性证据',
};

export const TASK_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '研究中',
  local_running: '本地研究中',
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
  completed: 'neutral',
  failed: 'warning',
  local_running: 'accent',
  cancel_requested: 'warning',
  cancelled: 'neutral',
  outcome_uncertain: 'warning',
  skipped: 'neutral',
};

export const ORDER_STATUS_TONES: Record<string, BadgeTone> = {
  Open: 'neutral',
  PartiallyFilled: 'accent',
  Filled: 'neutral',
  Rejected: 'warning',
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
  skipped_superseded: '已跳过 · 已被新源日替代',
  skipped_paused: '已跳过 · Agent 暂停',
  not_triggered: '尚未触发',
};

export const AVAILABILITY_LABELS: Record<string, string> = {
  not_verified: '未验证',
  available: '可用',
  last_task_completed: '最近调用完成',
  unavailable: '不可用',
  unavailable_or_outcome_unknown: '状态未知，可能含未结费用',
};

export const AVAILABILITY_TONES: Record<string, BadgeTone> = {
  not_verified: 'neutral',
  available: 'success',
  last_task_completed: 'success',
  unavailable: 'warning',
  unavailable_or_outcome_unknown: 'warning',
};

export const VERIFICATION_LABELS: Record<string, string> = {
  FAKE_SYNTHETIC_ONLY: 'FAKE / SYNTHETIC',
  REAL_PROVIDER_NOT_VERIFIED: '真实服务尚未验证',
  REAL_PROVIDER_CALL_OBSERVED: '已有真实调用记录',
  LOCAL_NO_BILLING: '本地不计费',
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
