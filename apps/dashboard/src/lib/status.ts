/**
 * 统一状态体系：主界面只出现 5 种状态（正常 / 进行中 / 需要处理 / 出错 / 未设置）。
 * 后端枚举只在这里映射为中文；禁止在页面里直接渲染原始枚举值。
 * 原始值保留在“诊断信息”折叠区。
 */
import type { IconName } from '../icons';
import type { AgentStatus, ApiErrorBody, SnapshotMeta } from './types';
import type { RuntimeStatus } from './runtime';

export type StatusKind = 'ok' | 'progress' | 'attention' | 'error' | 'unset';

export interface StatusView {
  kind: StatusKind;
  label: string;
  /** 一句话原因 / 现状。出错与需要处理时必须尽量提供。 */
  reason?: string;
}

export const STATUS_KIND_LABEL: Record<StatusKind, string> = {
  ok: '正常',
  progress: '进行中',
  attention: '需要处理',
  error: '出错',
  unset: '未设置',
};

export const STATUS_KIND_ICON: Record<StatusKind, IconName> = {
  ok: 'check',
  progress: 'activity',
  attention: 'alert-triangle',
  error: 'alert-octagon',
  unset: 'info',
};

export function statusView(kind: StatusKind, label: string, reason?: string): StatusView {
  return reason === undefined || reason === '' ? { kind, label } : { kind, label, reason };
}

/** 后端原因码 → 一句人话。未知代码返回 null，由调用方决定“原因未记录”。 */
const REASON_TEXT: Record<string, string> = {
  // 研究任务
  RESEARCH_SAVED: '研究结论已保存',
  RESEARCH_BLOCKED: '研究条件不满足，已停止',
  TASK_CANCELLED: '任务已取消',
  TASK_TIMEOUT: '研究任务超时',
  PROVIDER_TIMEOUT: 'AI 服务响应超时',
  PROVIDER_UNREACHABLE: '无法连接 AI 服务',
  PROVIDER_NOT_CONFIGURED: '尚未配置 AI 服务',
  PROVIDER_KEY_REJECTED: 'API Key 无效',
  PROVIDER_KEY_INVALID: 'API Key 格式不正确',
  PROVIDER_KEY_REQUIRED: '请先填写 API Key',
  PROVIDER_REQUIRED: '请先选择 AI 服务商',
  PROVIDER_PROFILE_INVALID: 'AI 服务配置已损坏',
  PROVIDER_UNSUPPORTED: '暂不支持该 AI 服务',
  PROVIDER_RESPONSE_INVALID: 'AI 服务返回了无法识别的内容',
  PROVIDER_CLIENT_UNAVAILABLE: '无法初始化 AI 服务连接',
  PROVIDER_HTTP_401: 'AI 服务拒绝了这次请求（认证失败）',
  PROVIDER_HTTP_403: 'AI 服务拒绝了这次请求（权限不足）',
  PROVIDER_HTTP_429: 'AI 服务请求过多，请稍后再试',
  PROVIDER_HTTP_500: 'AI 服务暂时不可用',
  PROVIDER_HTTP_502: 'AI 服务暂时不可用',
  PROVIDER_HTTP_503: 'AI 服务暂时不可用',
  // 预算
  DAILY_BUDGET_EXHAUSTED: '今日研究预算已用完',
  MONTHLY_BUDGET_EXHAUSTED: '本月研究预算已用完',
  TASK_BUDGET_EXHAUSTED: '本任务预算已用完',
  BILLING_OVERRUN_REQUIRES_OWNER: '费用超出预留，需要你核对账单',
  // 权限与外部发送
  REAL_MARKET_DATA_EGRESS_DENIED: '尚未授权向 AI 服务发送行情数据',
  OWNER_PAUSED: 'AI 研究已暂停',
  OWNER_TOKEN_REQUIRED: '本机会话已失效，请重新打开页面',
  APPROVAL_EXPIRED: '本次许可已过期',
  APPROVAL_STATE_CONFLICT: '状态已变化，请重新读取',
  DESKTOP_AGENT_AUTHORITY_MISMATCH: '研究实例与当前账户不匹配，已阻止执行',
  DESKTOP_BINDING_UNAVAILABLE: '研究实例绑定不可用，未执行研究',
  DEEPSEEK_DISABLED_OR_ONCE_CONSUMED: '云调用开关已关闭或本次许可已使用',
  LOCAL_CPU_DISABLED: '本地预测引擎已停用',
  LOCAL_NO_BILLING: '本地运行，不产生费用',
  // 账户 / 数据
  NO_SNAPSHOT: '尚未选择模拟账户数据',
  INVALID_SNAPSHOT: '模拟账户数据不可用',
  SNAPSHOT_CHANGED: '数据在读取期间发生变化，请重新读取',
  CURRENT_PAPER_ACCOUNT_UNCONFIGURED: '尚未配置模拟账户',
  INVALID_CURRENT_LEDGER: '模拟账户账本不可用',
  OFFLINE: '无法连接本地服务',
  TIMEOUT: '本地服务响应超时',
  INVALID_RESPONSE: '本地服务返回了无法识别的内容',
  API_ERROR: '本地服务返回了错误',
  RUNTIME_NOT_MANAGED: '这次启动没有启用后台任务',
  RUNTIME_REQUEST_FAILED: '后台任务读取失败',
  RUNTIME_ACTION_FAILED: '后台操作失败',
  UPDATE_CHECK_FAILED: '检查更新失败',
  WSL_DETECT_FAILED: '自动检测未完成',
  WSL_PROBE_FAILED: '本地预测引擎检测未完成',
  WSL_PROBE_REQUIRED: '需要先检测本地预测引擎',
  TIMESFM_WSL_NOT_CONFIGURED: '尚未配置本地预测引擎',
  TIMESFM_WSL_CONFIG_INCOMPLETE: '本地预测引擎配置不完整',
  TIMESFM_WSL_UNAVAILABLE: '无法调用 WSL，本地预测不可用',
  TIMESFM_WSL_DISTRO_MISSING: '配置的 WSL 发行版不存在',
  TIMESFM_WSL_VENV_MISSING: 'WSL 工作树缺少 Python 环境',
  TIMESFM_WSL_MODEL_MISSING: 'WSL 中没有找到本地预测模型',
  TIMESFM_WSL_TIMEOUT: '本地预测引擎超时，已安全停止',
  TIMESFM_WSL_CODE_MISMATCH: '本地预测引擎版本与安装包不一致',
  TIMESFM_WSL_PROTOCOL_INVALID: '本地预测引擎返回了无效结果',
  TIMESFM_WSL_MODEL_LINK_UNSUPPORTED: '模型文件所在磁盘不支持安全链接',
  MODEL_NOT_PROVISIONED: '本地预测模型校验失败',
  PYTHON_RUNTIME_MISSING: '缺少随安装包提供的 Python 运行时',
  DASHBOARD_EXITED: '页面服务异常退出，后台会自动重启',
  DASHBOARD_START_FAILED: '页面服务未能启动，请检查端口与安装文件',
  DASHBOARD_BINARY_MISSING: '安装目录缺少页面服务程序',
  PORT_IN_USE_BY_OTHER_APPLICATION: '端口被其他程序占用',
  EXTERNAL_STRATIDE_INSTANCE: '已有另一个 Stratide 实例在运行',
  EOD_NOT_CONFIGURED: '尚未初始化行情自动采集',
  WATCH_EXITED: '行情自动采集已退出，后台会自动重启',
  WATCH_RESTARTING: '正在按新配置重启行情自动采集',
  STARTING: '正在启动本机服务',
  DASHBOARD_STARTING: '服务已启动，正在等待健康检查',
  STOPPED_BY_OWNER: '后台服务已停止',
  STOPPED_WITH_UNMANAGED_SERVICE: '后台已停止，但仍有未受管理的实例在运行',
  CONTROL_INVALID: '操作参数无效',
  CONTROL_NOT_ALLOWED: '当前状态不允许这个操作',
  TASK_REQUEST_KEY_INVALID: '请求编号无效，请重试',
  TASK_INPUT_INVALID: '任务信息不完整，请检查后重试',
  NOTIFICATION_INPUT_LIMIT: '一次最多标记 50 条通知',
  // 工作区 / 研究报告
  WORKSPACE_SCHEMA: '研究报告版本不兼容',
  NOT_CONFIGURED: '尚未配置',
  // 全市场研究阻断（真实安装出现过）
  LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE: '行情目录为晚到或回填数据，不能作为当日研究依据',
  MARKET_RESEARCH_LOCAL_FAILURE: '本地研究阶段出现异常，研究已安全停止',
  MARKET_RESEARCH_SCOPE_INVALID: '当前输入用途不在研究授权范围内',
  NO_FROZEN_MARKET_SNAPSHOT: '当日没有可用的冻结行情快照',
  MARKET_HISTORY_CONTEXT_UNAVAILABLE: '连续交易日数据不足，暂时无法形成研究上下文',
  MARKET_HISTORY_NOT_READY_AT_DECISION: '最新行情快照在决策时点尚未就绪',
  MARKET_HISTORY_SOURCE_BLOCKED: '行情数据源被阻断，研究已停止',
  NO_QUALIFIED_RESEARCH_CANDIDATES: '当日没有符合条件的研究候选',
  SCREEN_IMPLEMENTATION_CHANGED_NEW_RUN_REQUIRED: '筛选规则已变化，需要重新运行研究',
  AUTOMATIC_CLOUD_DISABLED: '自动云端研究已关闭',
  TIMESFM_PARTIAL_OR_FAILED: '本地预测引擎部分失败，研究已停止',
  MARKET_DAY_NOT_QUALIFIED: '当日行情数据不满足研究条件',
  CATALOG_SCOPE_NOT_VERIFIED: '证券目录范围尚未核验',
  SOURCE_NOT_AVAILABLE_AT_DECISION: '数据在决策时点尚不可用',
  MARKET_RESEARCH_DISABLED: '全市场自动研究已关闭',
  MARKET_PARENT_BINDING: '研究输入与本地预测结果不一致，云端研究已停止',
  MARKET_RUN_CHANGED: '研究输入在运行期间发生变化，本轮研究已停止',
  MARKET_RESEARCH_PLAN_CHANGED: '本地预测计划已变化，正在重新准备研究',
  LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED: '本地预测输入已更新，需要重新运行',
  HISTORY_CONTEXT_CALENDAR: '连续交易日上下文不完整，研究已停止',
  PAPER_POLICY_ENSURE_FAILED: '自动启用模拟交易失败，模拟成交暂停',
  PAPER_MODULE_UNAVAILABLE: '模拟交易模块暂不可用',
  PAPER_MARKET_SNAPSHOT_REQUIRED: '还没有可用的行情快照，暂无法启用模拟交易',
  PAPER_UNIVERSE_UNAVAILABLE: '可用证券范围为空，暂无法启用模拟交易',
  PAPER_POLICY_CONFIGURE_REJECTED: '模拟账户拒绝了默认策略配置',
  OWNER_PORTFOLIO_POLICY_REQUIRED: '模拟交易尚未启用',
  OWNER_BATCH_CAPACITY_SCOPE_REQUIRED: '模拟交易策略缺少批次容量范围',
  MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE: '安装版由后台自动研究执行任务，手动新建研究暂不可用',
  NO_NEW_VALID_CURRENT_EOD_SOURCE: '今天还没有新的可用收盘数据',
  // 预算 / 授权 / 模型
  BUDGET_CURRENCY_TIMEZONE_IMMUTABLE: '预算币种与时区创建后不可修改',
  BUDGET_CONFIG_INVALID: '预算配置无效',
  AUTHORIZATION_REQUIRED: '研究模型尚未获得授权',
  PRICE_UNCONFIGURED: '研究模型没有配置费率',
  PRICE_UNBOUNDED: '研究模型费率缺少上限',
  PINNED_MODEL_UNAVAILABLE: '已冻结的研究模型当前不可用',
  PINNED_MODEL_CONFIGURATION_CHANGED: '研究模型配置在任务期间发生变化',
  DEFAULT_MODEL_UNCONFIGURED: '尚未设置默认研究模型',
  DEFAULT_MODEL_UNAVAILABLE: '默认研究模型当前不可用',
  MODEL_NOT_CONFIGURED: '尚未配置研究模型',
  MODEL_SELECTION_INVALID: '研究模型选择无效',
  MARKET_MODEL_REQUIRED: '全市场研究需要先配置研究模型',
  MARKET_MODEL_INVALID: '全市场研究模型配置无效',
  PROVIDER_KEY_MISSING: '缺少 AI 服务密钥',
  PROVIDER_DNS_UNAVAILABLE: '无法解析 AI 服务地址',
  PROVIDER_NETWORK_TARGET_REJECTED: 'AI 服务地址被拒绝',
  ENDPOINT_INVALID: 'AI 服务地址无效',
  ENDPOINT_REQUIRED: '缺少 AI 服务地址',
  ENDPOINT_NOT_ALLOWED: '不允许使用该 AI 服务地址',
  INPUT_TOKEN_BOUND_EXCEEDED: '输入内容超过模型上限',
  PROVIDER_RESPONSE_TOO_LARGE: 'AI 服务返回内容过大',
  PROVIDER_OUTPUT_OR_USAGE_INVALID: 'AI 服务返回内容或用量无法识别',
  PROVIDER_TRANSPORT_OUTCOME_UNKNOWN: 'AI 服务结果未知，可能已经产生费用',
  PROVIDER_HTTP_429_BILLING_UNKNOWN: 'AI 服务限流，是否计费未知',
  PROVIDER_HTTP_5XX_BILLING_UNKNOWN: 'AI 服务故障，是否计费未知',
  PROVIDER_HTTP_REDIRECT_REJECTED_BILLING_UNKNOWN: 'AI 服务重定向被拒绝，是否计费未知',
  PROVIDER_HTTP_ERROR_BILLING_UNKNOWN: 'AI 服务返回错误，是否计费未知',
  PROVIDER_INVALID_JSON_BILLING_UNKNOWN: 'AI 服务返回格式异常，是否计费未知',
  PROVIDER_BODY_INTERRUPTED: 'AI 服务响应中断，结果未知',
  MARKET_PROVIDER_OUTCOME_UNKNOWN: '云端研究结果未知，可能已经产生费用',
  MARKET_PROVIDER_HTTP_OUTCOME_UNKNOWN: '云端研究请求结果未知',
  MARKET_PROVIDER_BODY_UNKNOWN: '云端研究返回内容未知',
  MARKET_PROVIDER_RESPONSE_REJECTED_NO_RETRY: '云端返回内容被拒绝，不会自动重试',
  RETRY_UNSAFE_OR_EXHAUSTED: '该任务不能安全重试，或重试次数已用完',
  CALL_STATE_INVALID: '调用记录状态异常',
  CLOUD_SINGLE_ATTEMPT_REQUIRED: '云端调用只允许一次，不能自动重试',
  RESEARCH_STORAGE_LIMIT: '研究存储空间已满',
  TASK_STORAGE_LIMIT: '任务数量已达到上限',
  INPUT_INVALID: '研究输入无效',
  RESEARCH_OUTPUT_INVALID: '研究输出格式无效',
  RISK_PORTFOLIO_OUTPUT_REQUIRED: '缺少风险组合研究输出',
  FUSION_OUTPUT_REQUIRED: '缺少融合研究输出',
  STRUCTURED_RECEIPT_REQUIRED: '缺少结构化研究回执',
  PROVIDER_BILLING_BOUND_VIOLATION: '费用超出预留上限，需要人工核对',
  OWNER_CANCEL_REQUESTED: '已请求取消',
  OWNER_CANCELLED_BEFORE_REQUEST: '在发出请求前已取消',
  OWNER_DISABLED: '研究功能已关闭',
  CANCELLED_BEFORE_DISPATCH: '在发送前已取消',
  RESERVATION_INVALID: '预算预留无效',
  TIMEZONE_INVALID: '时区设置无效',
  TASK_NOT_CANCELLABLE: '当前状态不能取消',
  TASK_RETRY_UNSAFE_OR_EXHAUSTED: '当前状态不能安全重试',
  TASK_REQUEST_KEY_CONFLICT: '重复的请求编号',
  NOTIFICATION_NOT_FINISHED: '任务尚未结束，不能标记为已读',
  AGENT_STORAGE_UNAVAILABLE: '本机研究存储不可用',
  DESKTOP_BRIDGE_UNAVAILABLE: '桌面研究桥不可用',
  DESKTOP_READ_FAILED: '读取本机研究资料失败',
  DESKTOP_SOURCE_INVALID: '研究资料格式无效',
  RESTART_BEFORE_DISPATCH: '服务重启，任务在发送前中断',
  RESTART_AFTER_DISPATCH: '服务重启，任务发送后结果未知',
  RESTART_EXTERNAL_OUTCOME_UNKNOWN: '服务重启，外部调用结果未知',
  RESTART_CANCELLED_BEFORE_DISPATCH: '服务重启，任务在发送前取消',
  RECOVERED_BEFORE_DISPATCH: '服务恢复，任务在发送前中断',
  DAEMON_RESTART_RECONCILE_ORIGINAL_TASK: '后台重启，需要重新核对原任务',
  FAKE_CONFIRMED_NOT_SENT: '本地测试未真实发送',
  FAKE_PERMANENT_REJECTION: '本地测试模拟永久拒绝',
  FAKE_TIMEOUT_AFTER_POSSIBLE_CHARGE: '本地测试模拟超时，可能已计费',
  // 订单/模拟执行原因（混合中英文，NO_FILL 系列来自账本引擎）
  'NO_FILL / MISSING_QUOTE': '没有成交：缺少行情报价',
  'NO_FILL / EXPIRED_DELIVERY_WINDOW': '没有成交：已超过可成交时间',
  NO_FILL: '没有成交',
  MAX_SYMBOL_VALUE: '超过单只证券的市值上限',
  COST_UNKNOWN: '成本无法确认，未提交',
  RESEARCH_NOT_READY_84_SESSIONS_REQUIRED: '研究尚未就绪，暂不生成模拟订单',
  MISSING_QUOTE: '缺少行情报价',
};

export function humanReasonText(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (Object.hasOwn(REASON_TEXT, value)) return REASON_TEXT[value];
  if (value.startsWith('SOURCE_BLOCKED:')) return '数据源被阻断，暂时无法模拟成交';
  if (value.startsWith('OWNER_INVOICE:')) return '账单已人工核对';
  // 纯 ASCII 的未知文本视为后端码：不直接渲染，只进诊断；中文句子原样展示。
  return /^[\x20-\x7E]+$/.test(value) ? null : value;
}

/** 失败场景的一句话原因；拿不到时按验收要求写“原因未记录”。 */
export function failureReasonText(value: string | null | undefined): string {
  return humanReasonText(value) ?? '原因未记录';
}

export function taskStatusView(status: string, reason: string | null, conclusion: string | null): StatusView {
  switch (status) {
    case 'queued':
      return statusView('progress', '排队中', '等待开始');
    case 'running':
    case 'local_running':
      return statusView('progress', '运行中');
    case 'cancel_requested':
      return statusView('attention', '正在取消', '已发出取消请求，等待当前步骤结束');
    case 'completed':
      return statusView('ok', '已完成', conclusion ?? humanReasonText(reason) ?? undefined);
    case 'failed':
      return statusView('error', '运行失败', failureReasonText(reason));
    case 'blocked':
      return statusView('attention', '已被阻止', failureReasonText(reason));
    case 'outcome_uncertain':
      return statusView('attention', '结果未确认', '结果或费用尚未确认，请核对调用记录');
    case 'cancelled':
      return statusView('unset', '已取消');
    case 'skipped':
      return statusView('unset', '已跳过', humanReasonText(reason) ?? undefined);
    default:
      return statusView('unset', '状态未知');
  }
}

export function eodStatusView(disposition: string | null, reason: string | null): StatusView {
  switch (disposition) {
    case 'queued':
      return statusView('progress', '排队中');
    case 'running':
      return statusView('progress', '运行中');
    case 'completed':
      return statusView('ok', '已完成');
    case 'failed':
      return statusView('error', '运行失败', failureReasonText(reason));
    case 'outcome_uncertain':
      return statusView('attention', '结果未确认', '结果或费用尚未确认');
    case 'cancelled':
      return statusView('unset', '已取消');
    case 'skipped':
    case 'skipped_superseded':
    case 'skipped_paused':
      return statusView('unset', '已跳过', humanReasonText(reason) ?? undefined);
    case 'not_triggered':
      return statusView('unset', '尚未触发', '收盘后会自动运行');
    default:
      return statusView('unset', '尚无记录');
  }
}

const ORDER_STATUS: Record<string, StatusView> = {
  Open: statusView('progress', '待成交'),
  PartiallyFilled: statusView('progress', '部分成交'),
  Filled: statusView('ok', '已成交'),
  Rejected: statusView('error', '已拒绝'),
  Expired: statusView('unset', '已过期'),
};

export function orderStatusView(status: string, reason: string | null): StatusView {
  const base = ORDER_STATUS[status];
  if (!base) return statusView('unset', '状态未知');
  if (status === 'Rejected' && reason !== null) return { ...base, reason: humanReasonText(reason) ?? '原因未记录' };
  return base;
}

export function availabilityView(availability: string): StatusView {
  switch (availability) {
    case 'available':
      return statusView('ok', '正常');
    case 'last_task_completed':
      return statusView('ok', '最近调用正常');
    case 'not_verified':
      return statusView('attention', '尚未验证', '还没有成功调用记录');
    case 'unavailable':
      return statusView('error', '不可用');
    case 'unavailable_or_outcome_unknown':
      return statusView('attention', '结果未确认', '可能存在未结清费用');
    default:
      return statusView('unset', '状态未知');
  }
}

const DEPENDENCY_STATES: Record<string, StatusView> = {
  READY: statusView('ok', '正常'),
  CONFIGURED: statusView('ok', '正常'),
  INITIALIZED: statusView('ok', '正常'),
  COMPLETE: statusView('ok', '正常'),
  RUNNING: statusView('ok', '正常'),
  MISSING: statusView('attention', '未设置'),
  NOT_CONFIGURED: statusView('attention', '未设置'),
  DEGRADED: statusView('attention', '需要处理'),
  EXTERNAL_WSL_WORKSPACE_REQUIRED: statusView('attention', '需要处理'),
  BINDING_INVALID_OR_MISSING_LEDGER: statusView('attention', '需要处理'),
  BLOCKED_MISSING_RUNTIME: statusView('attention', '需要处理'),
  UNKNOWN: statusView('unset', '状态未知'),
  BROKEN: statusView('error', '出错'),
  UNAVAILABLE: statusView('error', '出错'),
  FAILED: statusView('error', '出错'),
};

export function dependencyStatusView(
  key: string,
  state: string,
  reason: string | null,
  note: string | null,
): StatusView {
  // 少数依赖的同一 state 含义不同：AI 研究服务/模拟账户未配置是“未设置”，
  // 而 Tushare 凭据缺失是“需要处理”（不补就采集不到数据）。
  if (key === 'timesfm' && state === 'CONFIGURED') {
    return statusView('attention', '需要处理', '已保存本地预测引擎入口，需检测后确认可用');
  }
  if ((key === 'market_eod' || key === 'paper_account' || key === 'agent') && (state === 'NOT_CONFIGURED' || state === 'MISSING')) {
    return statusView('unset', '未设置', humanReasonText(reason) ?? note ?? undefined);
  }
  const base = Object.hasOwn(DEPENDENCY_STATES, state)
    ? DEPENDENCY_STATES[state]
    : state.startsWith('BLOCKED')
      ? statusView('attention', '需要处理')
      : statusView('unset', '状态未知');
  const detail = humanReasonText(reason) ?? note;
  return detail === null || detail === '' ? { ...base } : { ...base, reason: detail };
}

export const DEPENDENCY_LABELS: Record<string, string> = {
  python: 'Python 运行时',
  wsl: 'WSL 环境',
  timesfm: '本地预测引擎',
  tushare_credential: 'Tushare 数据源',
  market_eod: '行情自动采集',
  paper_account: '模拟账户',
  agent: 'AI 研究服务',
};

export const DEPENDENCY_ORDER = ['python', 'wsl', 'timesfm', 'tushare_credential', 'market_eod', 'paper_account', 'agent'] as const;

export interface OverallInput {
  serviceOnline: boolean;
  healthChecking: boolean;
  healthErrorCode: string | null;
  runtime: RuntimeStatus | null;
  runtimeErrorCode: string | null;
}

export interface OverallStatus {
  status: StatusView;
  /** 需要处理/出错的条目名称，用于“一句话 + 展开原因”。 */
  problems: string[];
  /** 全部正常的组件数量，用于展示 7/7。 */
  readyCount: number;
  totalCount: number;
}

export function overallSystemStatus(input: OverallInput): OverallStatus {
  const problems: string[] = [];
  if (input.healthErrorCode !== null) {
    return {
      status: statusView('error', '服务已断开', humanReasonText(input.healthErrorCode) ?? '无法连接本地服务'),
      problems: ['本地服务'],
      readyCount: 0,
      totalCount: 7,
    };
  }
  if (input.healthChecking && !input.serviceOnline) {
    return { status: statusView('progress', '正在检查'), problems: [], readyCount: 0, totalCount: 7 };
  }
  if (input.runtimeErrorCode === 'RUNTIME_NOT_MANAGED') {
    return {
      status: statusView('attention', '后台任务未启用', '这次是命令行启动：登录自启、行情自动采集与历史补录不可用。'),
      problems: ['后台任务'],
      readyCount: 0,
      totalCount: 7,
    };
  }
  if (input.runtime === null) {
    return { status: statusView('progress', '正在读取系统状态'), problems: [], readyCount: 0, totalCount: 7 };
  }
  const runtime = input.runtime;
  if (runtime.supervisor.status === 'STOPPED' || runtime.supervisor.status === 'NOT_STARTED') {
    return {
      status: statusView('unset', '后台任务未运行', humanReasonText(runtime.supervisor.reason) ?? '行情自动采集与 AI 研究不会开始'),
      problems: ['后台任务'],
      readyCount: 0,
      totalCount: DEPENDENCY_ORDER.length,
    };
  }
  if (runtime.supervisor.status === 'DEGRADED' || runtime.supervisor.status === 'BLOCKED') {
    return {
      status: statusView('attention', '后台任务需要处理', humanReasonText(runtime.supervisor.reason) ?? undefined),
      problems: ['后台任务'],
      readyCount: 0,
      totalCount: DEPENDENCY_ORDER.length,
    };
  }
  let readyCount = 0;
  let hasError = false;
  for (const key of DEPENDENCY_ORDER) {
    const dependency = runtime.dependencies[key];
    const view = dependencyStatusView(key, dependency.state, dependency.reason ?? null, dependency.note ?? null);
    if (view.kind === 'ok') readyCount += 1;
    else if (view.kind === 'error' || view.kind === 'attention') {
      problems.push(DEPENDENCY_LABELS[key] ?? key);
      if (view.kind === 'error') hasError = true;
    }
  }
  if (!runtime.service.healthy && !hasError) {
    return {
      status: statusView('error', '本地服务已断开', humanReasonText(runtime.supervisor.reason) ?? undefined),
      problems: [...problems, '本地服务'],
      readyCount,
      totalCount: DEPENDENCY_ORDER.length,
    };
  }
  if (hasError) {
    return {
      status: statusView('error', '有组件出错', '需要在“系统与诊断”中处理：' + problems.join('、')),
      problems,
      readyCount,
      totalCount: DEPENDENCY_ORDER.length,
    };
  }
  if (problems.length > 0) {
    return {
      status: statusView('attention', '有组件需要处理', '查看“系统与诊断”：' + problems.join('、')),
      problems,
      readyCount,
      totalCount: DEPENDENCY_ORDER.length,
    };
  }
  return {
    status: statusView('ok', '运行正常', '所有依赖与后台任务均正常'),
    problems,
    readyCount,
    totalCount: DEPENDENCY_ORDER.length,
  };
}

export interface ResearchStatusInput {
  ready: boolean;
  paused: boolean;
  status: AgentStatus | null;
  errorCode: string | null;
  runningTasks: number;
  /** 最近一个已结束任务的状态与原因：用于如实显示“最近一次研究未运行”。 */
  latestTaskStatus?: string | null;
  latestTaskReason?: string | null;
}

export function researchStatusView(input: ResearchStatusInput): StatusView {
  if (!input.ready || input.status === null) {
    if (input.errorCode === null) return statusView('progress', '正在读取');
    if (input.errorCode === 'AGENT_NOT_CONFIGURED') return statusView('attention', '未设置', '尚未配置 AI 研究服务');
    return statusView('error', '无法读取', humanReasonText(input.errorCode) ?? undefined);
  }
  const status = input.status;
  if (status.paused) return statusView('attention', '已暂停', '暂停期间不会开始新的研究');
  if (status.worker_error !== null) {
    return statusView('error', '研究服务出错', failureReasonText(status.worker_error));
  }
  if (!status.models.some((model) => model.id === status.default_model)) {
    return statusView('attention', '需要设置', '尚未选择默认研究模型');
  }
  if (status.budget.state !== 'configured') {
    return statusView('attention', '需要设置', '还没有设置研究预算');
  }
  if (input.runningTasks > 0) {
    return statusView('progress', '研究进行中', input.runningTasks + ' 个任务正在运行');
  }
  if (input.latestTaskStatus === 'blocked' || input.latestTaskStatus === 'failed' || input.latestTaskStatus === 'outcome_uncertain') {
    const view = taskStatusView(input.latestTaskStatus, input.latestTaskReason ?? null, null);
    return statusView('attention', '最近一次研究未运行', view.reason ?? '可在 AI 研究页查看原因');
  }
  return statusView('ok', '正常', '等待新的研究任务');
}

export const FREEZE_REASON_LABEL: Record<string, string> = {
  DailyLoss: '当日亏损达到限制',
  Drawdown: '账户回撤达到限制',
  OrderUncertainty: '订单状态不确定',
  Manual: '人工暂停交易',
};

export function freezeReasonLabel(reason: string): string {
  return FREEZE_REASON_LABEL[reason] ?? '交易保护限制';
}

export interface ProtectionInput {
  /** AccountData.risk；null = 这份数据没有附带交易保护信息，不能当作安全。 */
  risk: { account_freezes: unknown[] | null; strategy_freezes: unknown[] | null } | null;
  dataMissing: boolean;
}

export function protectionStatusView(input: ProtectionInput): StatusView {
  if (input.risk === null || input.risk.account_freezes === null || input.risk.strategy_freezes === null) {
    return statusView('unset', '交易保护状态未记录', '这份数据没有附带交易保护信息，不能据此判断账户是否安全');
  }
  const account = input.risk.account_freezes.map((item) => String(item));
  const strategy = input.risk.strategy_freezes.map((item) => String(item));
  const total = account.length + strategy.length;
  if (total > 0) {
    const labels = [...account, ...strategy].map(freezeReasonLabel);
    const unique = Array.from(new Set(labels));
    return statusView('attention', '交易保护已触发', unique.join('、') + '；新的模拟下单会被阻止');
  }
  if (input.dataMissing) return statusView('attention', '数据缺失', '数据恢复前无法可靠估值');
  return statusView('ok', '交易保护正常', '当前没有触发限制');
}

export function supervisorStatusView(status: string, reason: string | null): StatusView {
  switch (status) {
    case 'RUNNING':
      return statusView('ok', '运行中');
    case 'STARTING':
    case 'STOPPING':
      return statusView('progress', status === 'STARTING' ? '正在启动' : '正在停止');
    case 'DEGRADED':
    case 'BLOCKED':
      return statusView('attention', '需要处理', humanReasonText(reason) ?? undefined);
    case 'STOPPED':
      return statusView('unset', '已停止');
    case 'NOT_STARTED':
      return statusView('unset', '未启动');
    default:
      return statusView('unset', '状态未知');
  }
}

export interface DataStatusInput {
  meta: SnapshotMeta | null;
  errorCode: string | null;
  errorMessage: string | null;
  gaps: number;
}

export function dataStatusView(input: DataStatusInput): StatusView {
  if (input.meta === null) {
    if (input.errorCode === null) return statusView('progress', '正在读取');
    if (input.errorCode === 'NO_SNAPSHOT' || input.errorCode === 'CURRENT_PAPER_ACCOUNT_UNCONFIGURED') {
      return statusView('attention', '未设置', humanReasonText(input.errorCode) ?? undefined);
    }
    return statusView('error', '读取失败', humanReasonText(input.errorCode) ?? humanReasonText(input.errorMessage) ?? '原因未记录');
  }
  if (input.gaps > 0) return statusView('attention', '数据有缺失', '有 ' + input.gaps + ' 个数据缺口');
  return statusView('ok', '数据正常');
}

/** 研究数据模式的诊断用标签：只在诊断折叠区出现。 */
export const MODE_DIAGNOSTIC_LABEL: Record<string, string> = {
  tushare_incremental_eod: '盘后行情增量采集',
  ex_post_paper_assumption: '次日开盘价模拟成交假设',
  historical_research_only: '事后历史研究数据',
  forward_observed_eod: '前向盘后观察',
  synthetic_test: '本地测试数据（合成）',
  historical_replay: '历史回放',
  forward_paper: '前向模拟',
};

export const EVIDENCE_DIAGNOSTIC_LABEL: Record<string, string> = {
  EX_POST_OPEN_ASSUMPTION: '次日开盘价模拟成交假设',
  exploratory_historical_replay_not_pit_verified: '历史回放，时点可用性未核验',
  engine_test_only: '引擎测试数据',
  exploratory_not_verified: '探索性，尚未独立核验',
  independent_verified: '独立核验',
  exploratory: '探索性',
};

export const WORKSPACE_STATE_LABEL: Record<string, string> = {
  not_configured: '尚未配置',
  RESEARCH_ONLY: '仅供研究',
  REGISTERED: '已登记',
  FROZEN_CANDIDATE: '候选已冻结',
  NOT_BILLED: '未计费',
  FROZEN_NOT_RUN: '已冻结，尚未运行',
  LOCAL_NO_BILLING: '本地运行，不产生费用',
  ESTIMATED_NOT_VERIFIED_BILL: '费用为估算，尚未核对账单',
  verified_local_integrity: '本地完整性已核对',
  stored_evidence_not_qualification: '有来源记录，不代表已获交易资格',
  historical_research_only: '历史研究数据',
  synthetic_test: '本地测试数据',
  forward_observed_eod: '前向盘后观察',
  BLOCKED: '已阻止',
  ready: '可读取',
};

/** 通知里的状态 → “发生了什么”标题。 */
export function notificationTitle(status: string): string {
  switch (status) {
    case 'completed':
      return '研究任务已完成';
    case 'failed':
      return '研究任务失败';
    case 'cancelled':
      return '研究任务已取消';
    case 'outcome_uncertain':
      return '研究结果未确认';
    case 'running':
    case 'local_running':
      return '研究任务运行中';
    case 'queued':
      return '研究任务排队中';
    case 'pending':
      return '有一个操作等待批准';
    default:
      return '有新的研究动态';
  }
}

export function researchTaskName(createdAt: string | null, name: string | null): string {
  const date = createdAt === null ? '' : createdAt.slice(0, 10);
  const trimmed = name === null ? '' : name.trim();
  if (date === '' && trimmed === '') return '研究任务';
  if (date === '') return trimmed;
  if (trimmed === '') return date + ' 研究任务';
  return date + ' · ' + trimmed;
}

export type { ApiErrorBody };
