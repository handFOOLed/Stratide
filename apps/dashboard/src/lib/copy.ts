/**
 * 全站用户可见文案的唯一来源。
 * 规则见 docs/UI_TERMINOLOGY.md：同义词、内部词、后端枚举不得进入主界面。
 */

export const TERMS = {
  paperAccount: '模拟账户',
  aiResearch: 'AI 研究',
  closeAutoResearch: '收盘后自动研究',
  marketCollector: '行情自动采集',
  backgroundTasks: '后台任务',
  tradeProtection: '交易保护',
  dataNormal: '数据正常',
  dataDate: '数据日期',
  updatedAt: '更新于',
  dailyLedger: '每日账本',
  holdingsValue: '持仓市值',
  cashTransfers: '资金转入转出',
  initialCapital: '初始资金',
  frozenOrderCash: '挂单冻结资金',
  strategyVersion: '策略版本',
  researchReport: '研究报告',
  localPredictionEngine: '本地预测引擎（WSL）',
  simulatedFill: '按次日开盘价模拟成交',
} as const;

export const APP = {
  name: 'Stratide',
  tagline: '本地模拟盘与 AI 研究',
  localOnly: '仅本机访问',
} as const;

export const COMMON = {
  retry: '重新读取',
  loading: '正在读取…',
  loadFailed: '读取失败',
  cancel: '取消',
  confirm: '确认',
  close: '关闭',
  save: '保存',
  refresh: '刷新',
  copy: '复制',
  copied: '已复制',
  viewDetail: '查看详情',
  goToSettings: '去设置',
  notAvailable: '—',
  unknown: '未知',
  all: '全部',
} as const;

export const DIAGNOSTICS = {
  title: '诊断信息',
  hint: '默认收起，包含内部标识与原始状态，仅供排查问题。',
  copy: '复制诊断信息',
  copied: '诊断信息已复制',
  empty: '没有可显示的诊断信息。',
} as const;

export const HEALTH_BAR = {
  account: '模拟账户',
  dataDate: '数据更新至',
  system: '系统状态',
  research: 'AI 研究',
} as const;

/** 数量单位：统一通过 countText() 使用，不再手写“共 N 笔 / N 条 / N 只”。 */
export const UNITS = {
  fill: '笔',
  order: '笔',
  position: '只',
  task: '个',
  day: '天',
  item: '条',
} as const;

export const EMPTY = {
  fillsTitle: '还没有成交',
  fillsBody: '系统会在通过交易保护后，按次日开盘价模拟成交。',
  ordersTitle: '还没有订单',
  ordersBody: '系统通过交易保护后才会提交模拟订单。',
  positionsTitle: '当前空仓',
  positionsBody: '没有持仓时，这里会保持为空。',
  dailyTitle: '还没有每日记录',
  dailyBody: '每个交易日收盘后，账本会自动更新。',
  tasksTitle: '还没有研究任务',
  tasksBody: '新建研究后，任务进度与结论会显示在这里。',
  noticesTitle: '还没有通知',
  noticesBody: '研究任务完成、失败或需要处理时，会在这里提醒你。',
  reportsTitle: '还没有研究报告',
  reportsBody: '完成研究后，结论会保存在这里，供你回看。',
  chartTitle: '资产曲线会在第二个交易日出现',
  chartBody: '现在只有 1 个数据日；每天收盘更新后，曲线会自动延长。',
} as const;
