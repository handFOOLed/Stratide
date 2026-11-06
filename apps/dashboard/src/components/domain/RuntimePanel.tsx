import { useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { CardBody } from '../ui/Card';
import { CopyButton, Diagnostics } from '../ui/Diagnostics';
import { Field, TextInput } from '../ui/Field';
import { Modal } from '../ui/Overlay';
import { ProgressBar } from '../ui/ProgressBar';
import { StatusBadge } from '../ui/StatusBadge';
import { Switch } from '../ui/Switch';
import { useToast } from '../ui/Toast';
import { Icon } from '../../icons';
import { countText, formatDateTime, formatDay } from '../../lib/format';
import {
  DEPENDENCY_LABELS,
  DEPENDENCY_ORDER,
  dependencyStatusView,
  humanReasonText,
  overallSystemStatus,
  statusView,
  supervisorDisplayView,
} from '../../lib/status';
import type { StatusView } from '../../lib/status';
import { runtimeAction, setSetupComplete } from '../../lib/runtime';
import type { DependencyStatus, RuntimeStatus, WslProbeResult } from '../../lib/runtime';
import { ApiError } from '../../lib/api';
import type { HealthState } from '../../state/useHealth';
import type { RuntimeState } from '../../state/useRuntime';
import type { PaperDataState } from '../../state/usePaperData';
import type { AgentState } from '../../state/useAgent';
import { useTheme } from '../../state/ThemeProvider';

type DependencyKey = (typeof DEPENDENCY_ORDER)[number];

/** 依赖清单统一叫法：本地预测引擎（WSL）。 */
const TIMESFM_LABEL = '本地预测引擎（WSL）';

function dependencyLabel(key: DependencyKey): string {
  return key === 'timesfm' ? TIMESFM_LABEL : DEPENDENCY_LABELS[key];
}

function problemDisplayName(name: string): string {
  return name === DEPENDENCY_LABELS['timesfm'] ? TIMESFM_LABEL : name;
}

/** 首次设置“整块折叠”的判定：标记完成且关键依赖就绪。 */
const CRITICAL_DEPENDENCIES: readonly DependencyKey[] = ['python', 'tushare_credential', 'market_eod', 'paper_account'];
const BACKFILL_TARGET = 84;

const DEPENDENCY_OK: Record<DependencyKey, string> = {
  python: '运行正常',
  wsl: 'WSL 环境可用',
  timesfm: '本地预测引擎可用',
  tushare_credential: '访问令牌已设置',
  market_eod: '行情自动采集正常',
  paper_account: '模拟账户已设置',
  agent: 'AI 研究服务正常',
};

const DEPENDENCY_NEXT_STEP: Record<DependencyKey, string> = {
  python: '安装包可能不完整，请重新安装 Stratide',
  wsl: '需要安装 WSL 环境；未安装时本地预测不可用',
  timesfm: '可在“本地预测引擎（WSL）设置”中检测或手动填写',
  tushare_credential: '请在“首次设置”中填写 Tushare 访问令牌',
  market_eod: '行情采集尚未初始化，数据不会自动更新，请查看安装说明',
  paper_account: '模拟账户尚未设置，请按安装说明完成配置',
  agent: '请在“AI 服务与预算”中配置 AI 服务',
};

const DEPENDENCY_REASONS: Record<string, string> = {
  BUNDLED_PYTHON_MISSING: '缺少随安装包提供的 Python 运行时，请重新安装 Stratide',
  WSL_TERMINATED: 'WSL 环境已退出，请重试检测',
  CREDENTIAL_HELPER_MISSING: '缺少凭据检查组件，请重新安装 Stratide',
  CREDENTIAL_HELPER_INVALID: '无法检查 Tushare 访问令牌，请重新保存',
  TIMESFM_CPU_REQUIRES_THE_EXISTING_LINUX_WORKSPACE_ISOLATION: '尚未设置本地预测引擎；行情采集不受影响',
};

const ACTION_REASONS: Record<string, string> = {
  BACKFILL_ALREADY_RUNNING: '历史数据补齐已在进行中',
  BACKFILL_REQUEST_FAILED: '补齐请求未发出，请稍后重试',
  MARKET_COMMAND_FAILED: '行情采集操作未完成，请稍后重试',
  EOD_OPERATOR_MISSING: '行情采集组件缺失，请重新安装 Stratide',
  HELPER_TIMEOUT: '本机组件响应超时，请稍后重试',
  MARKET_INPUT_INVALID: '请求参数无效',
  TOKEN_INPUT_INVALID: '访问令牌格式不正确',
  CREDENTIAL_WRITE_FAILED: '访问令牌保存失败，请重试',
  AUTOSTART_OPERATION_FAILED: '登录自启设置未完成，请重试',
  LAUNCHER_MISSING: '缺少启动程序，请重新安装 Stratide',
  WSL_PATH_INVALID: 'WSL 路径格式不正确',
  WSL_DETECT_FAILED: '自动检测未完成，请重试',
  WSL_PROBE_FAILED: '本地预测引擎检测未完成，请重试',
  UPDATE_CHECK_MISSING: '缺少检查更新组件，请重新安装 Stratide',
  FOLDER_OPEN_FAILED: '无法打开文件夹，请稍后重试',
  PYTHON_RUNTIME_MISSING: '缺少 Python 运行时，请重新安装 Stratide',
  CREDENTIAL_HELPER_MISSING: '缺少凭据保存组件，请重新安装 Stratide',
  WSL_NOT_CONFIGURED: '尚未配置本地预测引擎，请先填写并保存设置',
  WSL_DETECT_OUTPUT_INVALID: '自动检测返回了无法识别的内容，请手动填写',
  TIMESFM_CLI_MISSING: '安装包缺少本地预测组件，请重新安装 Stratide',
  RUNTIME_CONFIG_INVALID: '运行配置无效，请检查安装',
};

interface UpdateCheckResult {
  state: string;
  tag?: string;
  url?: string;
}

interface DetectWslResult {
  state: string;
  wsl?: {
    distribution: string;
    workspace: string;
    python?: string | null;
    model?: string | null;
  };
}

function reasonText(code: string | null | undefined, extra: Record<string, string>): string | null {
  if (code === null || code === undefined || code === '') return null;
  if (Object.hasOwn(extra, code)) return extra[code];
  return humanReasonText(code);
}

function dependencyReasonText(dependency: DependencyStatus): string | null {
  const code = dependency.reason;
  if (code === undefined || code === null || code === '') return null;
  if (code.startsWith('PYTHON_EXIT_')) return 'Python 运行时无法启动，请重新安装 Stratide';
  if (code.startsWith('WSL_EXIT_')) return 'WSL 环境不可用，请检查 WSL 安装';
  if (code.startsWith('WSL_NOT_INSTALLED_OR_BLOCKED')) return '未检测到可用的 WSL 环境，可跳过本地预测功能';
  if (code.startsWith('CREDENTIAL_HELPER_EXIT_')) return '无法检查 Tushare 访问令牌';
  return reasonText(code, DEPENDENCY_REASONS);
}

function actionReasonText(code: string): string | null {
  if (Object.hasOwn(ACTION_REASONS, code)) return ACTION_REASONS[code];
  if (code.startsWith('MARKET_COMMAND_FAILED')) return '行情采集操作未完成，请稍后重试';
  if (code.startsWith('CREDENTIAL_WRITE_FAILED')) return '访问令牌保存失败，请重试';
  if (code.startsWith('UPDATE_CHECK_FAILED')) return '检查更新失败，请稍后重试';
  return humanReasonText(code);
}

/** 依赖状态 → 统一 5 态 + 一句人话原因 / 下一步；原始 reason 只进诊断信息。 */
function dependencyView(key: DependencyKey, dependency: DependencyStatus): StatusView {
  if (key === 'tushare_credential' && (dependency.state === 'ERROR' || dependency.state === 'INVALID')) {
    return statusView('error', '出错', '无法读取 Tushare 访问令牌，请重新保存');
  }
  const base = dependencyStatusView(key, dependency.state, dependency.reason ?? null, null);
  const reason = dependencyReasonText(dependency);
  if (reason !== null) return statusView(base.kind, base.label, reason);
  if (base.kind === 'ok') {
    if (key === 'wsl') {
      return statusView(
        'ok',
        base.label,
        dependency.configured === true
          ? 'WSL 环境可用；本地预测引擎设置已保存（请点“检查状态”确认引擎可用）'
          : 'WSL 环境可用；本地预测引擎尚未设置',
      );
    }
    return statusView('ok', base.label, DEPENDENCY_OK[key]);
  }
  if (base.kind === 'error') return statusView('error', base.label, '失败，原因未记录');
  if (base.kind === 'attention') return statusView('attention', base.label, DEPENDENCY_NEXT_STEP[key]);
  if (base.kind === 'progress') return statusView('progress', base.label, DEPENDENCY_NEXT_STEP[key]);
  if (dependency.state === 'UNKNOWN') return statusView('unset', base.label, '状态未知，请刷新或查看诊断信息');
  return statusView('unset', base.label, DEPENDENCY_NEXT_STEP[key]);
}

function supervisorView(supervisor: RuntimeStatus['supervisor']): StatusView {
  return supervisorDisplayView(supervisor.status, supervisor.reason);
}

function collectorView(status: RuntimeStatus, backfillRunning: boolean): StatusView {
  if (backfillRunning) return statusView('progress', '进行中', '历史数据补齐在进行，行情采集暂时暂停');
  const market = dependencyView('market_eod', status.dependencies.market_eod);
  if (market.kind === 'attention' || market.kind === 'error') return market;
  if (status.supervisor.watch !== null) return statusView('ok', '正常', '每个交易日收盘后自动采集');
  return statusView('attention', '未运行', '行情自动采集当前未运行，后台会自动重启');
}

function serviceView(health: HealthState): StatusView {
  if (health.error !== null) return statusView('error', '出错', humanReasonText(health.error.code) ?? '失败，原因未记录');
  if (health.data === null) return statusView('progress', '正在检查');
  return health.data.service === 'online'
    ? statusView('ok', '正常', '仅本机访问')
    : statusView('error', '出错', '无法连接本地服务');
}

/** 日志里的 ISO UTC 时间串 → Asia/Shanghai 本地时间，不显示 UTC/Z；没有时间戳的行原样保留。 */
function logLineText(line: string): string {
  return line.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/g, (value) => formatDateTime(value));
}

function normalizeVersion(value: string): string {
  return value.trim().replace(/^v/i, '');
}

/** 版本号 + 检查更新；系统与诊断、关于都复用这一块。 */
export function VersionCheck({ version, uiVersion, build }: { version: string; uiVersion?: string; build?: RuntimeStatus['build'] | null }) {
  const { push } = useToast();
  const [busy, setBusy] = useState(false);
  const [release, setRelease] = useState<{ tag: string; url: string | null; isLatest: boolean } | null>(null);

  const check = async () => {
    setBusy(true);
    try {
      const result = await runtimeAction<UpdateCheckResult>('update-check');
      if (result.state === 'OK' && result.tag !== undefined) {
        const isLatest = normalizeVersion(result.tag) === normalizeVersion(version);
        setRelease({ tag: result.tag, url: result.url ?? null, isLatest });
        push({ title: isLatest ? '已是最新版本' : '发现新版本 ' + result.tag, tone: isLatest ? 'info' : 'success' });
      } else if (result.state === 'NO_RELEASE') {
        push({ title: '暂时没有新版本信息', tone: 'info' });
      } else if (result.state === 'UNAVAILABLE') {
        push({ title: '无法检查更新（网络不可用）', tone: 'warning' });
      } else {
        push({ title: '暂时无法检查更新', tone: 'info' });
      }
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'UPDATE_CHECK_FAILED';
      push({ title: actionReasonText(code) ?? '失败，原因未记录', tone: 'danger' });
    } finally {
      setBusy(false);
    }
  };

  const buildLine =
    build === null || build === undefined || build.commit === null
      ? null
      : '构建 ' + build.commit.slice(0, 8) + (build.built_at === null ? '' : ' · ' + formatDateTime(build.built_at));

  return (
    <div className="runtime-version" data-testid="version">
      <span className="runtime-version__current">
        <span>
          版本 v{version}
          {uiVersion === undefined || uiVersion === version ? '' : ' · 界面 v' + uiVersion}
        </span>
        {buildLine === null ? null : <span className="runtime-version__build">{buildLine}</span>}
      </span>
      <Button size="sm" icon="refresh" loading={busy} onClick={() => void check()} data-testid="check-update">
        检查更新
      </Button>
      {release === null ? null : release.isLatest ? (
        <span className="runtime-version__latest">已是最新版本</span>
      ) : release.url === null ? (
        <span className="runtime-version__latest">发现新版本 {release.tag}</span>
      ) : (
        <a className="runtime-version__latest" href={release.url} target="_blank" rel="noreferrer">
          发现新版本 {release.tag}
        </a>
      )}
    </div>
  );
}

export function RuntimePanel({
  health,
  runtime,
  paper,
  agent,
}: {
  health: HealthState;
  runtime: RuntimeState;
  paper: PaperDataState;
  agent: AgentState;
}) {
  const { push } = useToast();
  const { theme } = useTheme();
  const status = runtime.status;
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [secret, setSecret] = useState('');
  const [wslForm, setWslForm] = useState({
    distribution: '',
    workspace: '',
    python: '.venv/bin/python',
    model: 'models/timesfm-2.5',
  });
  const [wslLoaded, setWslLoaded] = useState(false);
  const [wslProbe, setWslProbe] = useState<WslProbeResult | null>(null);
  const [confirm, setConfirm] = useState<'backfill' | 'setup' | 'setup-undo' | null>(null);

  useEffect(() => {
    if (status === null || wslLoaded) return;
    const wsl = status.dependencies.wsl;
    setWslForm({
      distribution: wsl.distribution ?? '',
      workspace: wsl.workspace ?? '',
      python: wsl.python ?? '.venv/bin/python',
      model: wsl.model ?? 'models/timesfm-2.5',
    });
    setWslLoaded(true);
  }, [status, wslLoaded]);

  const act = async (
    name: string,
    path: string,
    body: Record<string, unknown>,
    success: string,
    afterSuccess?: () => Promise<void>,
  ): Promise<boolean> => {
    setBusy(name);
    setActionError(null);
    try {
      await runtimeAction(path, body);
      push({ title: success, tone: 'success' });
      if (afterSuccess !== undefined) {
        await afterSuccess();
      } else {
        runtime.refresh();
      }
      return true;
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'RUNTIME_ACTION_FAILED';
      setActionError(code);
      push({ title: actionReasonText(code) ?? '失败，原因未记录', tone: 'danger' });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const detectWsl = async () => {
    setBusy('detect');
    setActionError(null);
    try {
      const result = await runtimeAction<DetectWslResult>('wsl-detect');
      if (result.state === 'FOUND') {
        if (result.wsl !== undefined) {
          setWslForm({
            distribution: result.wsl.distribution,
            workspace: result.wsl.workspace,
            python: result.wsl.python ?? '.venv/bin/python',
            model: result.wsl.model ?? 'models/timesfm-2.5',
          });
          setWslLoaded(true);
        }
        push({ title: '已检测到本地预测引擎，设置已自动保存', tone: 'success' });
        await probeWsl();
      } else {
        push({ title: '未检测到本地预测引擎', description: '行情采集不受影响；也可以在下方手动填写。', tone: 'warning' });
      }
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'WSL_DETECT_FAILED';
      setActionError(code);
      push({ title: actionReasonText(code) ?? '失败，原因未记录', tone: 'danger' });
    } finally {
      setBusy(null);
    }
  };

  const probeWsl = async () => {
    setBusy('probe');
    setActionError(null);
    try {
      const result = await runtimeAction<WslProbeResult>('wsl-probe');
      setWslProbe(result);
      push({
        title: result.state === 'READY' ? '本地预测引擎正常' : '本地预测引擎需要处理',
        description:
          result.state === 'READY' ? undefined : (humanReasonText(result.reason) ?? '原因未记录'),
        tone: result.state === 'READY' ? 'success' : 'danger',
      });
      runtime.refresh();
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'WSL_PROBE_FAILED';
      setActionError(code);
      push({ title: actionReasonText(code) ?? '失败，原因未记录', tone: 'danger' });
    } finally {
      setBusy(null);
    }
  };

  const openFolder = (target: 'data' | 'logs') => {
    void act(target, 'open-folder', { target }, target === 'data' ? '已打开数据目录' : '已打开日志目录');
  };

  const startBackfill = () => {
    void act('backfill', 'market', { action: 'backfill', sessions: BACKFILL_TARGET }, '历史补录已开始').then((ok) => {
      if (ok) setConfirm(null);
    });
  };

  /** 完成/撤销首次设置：后端只写运行目录标记，不动账户、研究、预算与行情数据。 */
  const runSetup = async (completed: boolean | null, success: string, busyKey: string): Promise<boolean> => {
    setBusy(busyKey);
    setActionError(null);
    try {
      await setSetupComplete(completed);
      push({ title: success, tone: 'success' });
      runtime.refresh();
      return true;
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'RUNTIME_ACTION_FAILED';
      setActionError(code);
      push({ title: actionReasonText(code) ?? '失败，原因未记录', tone: 'danger' });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const completeSetup = () => {
    void runSetup(null, '首次设置已完成', 'setup').then((ok) => {
      if (ok) setConfirm(null);
    });
  };

  const undoSetup = () => {
    void runSetup(false, '已撤销首次设置标记', 'setup-undo').then((ok) => {
      if (ok) setConfirm(null);
    });
  };

  const overall = overallSystemStatus({
    serviceOnline: health.data !== null && health.data.service === 'online' && health.error === null,
    healthChecking: health.checking,
    healthErrorCode: health.error === null ? null : health.error.code,
    runtime: status,
    runtimeErrorCode: runtime.error === null ? null : runtime.error.code,
  });

  const checkedAtText =
    runtime.checkedAt === null ? null : formatDateTime(new Date(runtime.checkedAt).toISOString());

  const problemView = (name: string): StatusView => {
    if (name === '本地服务') return serviceView(health);
    if (name === '后台任务') {
      return status === null ? statusView('progress', '正在读取') : supervisorView(status.supervisor);
    }
    const key = DEPENDENCY_ORDER.find((candidate) => DEPENDENCY_LABELS[candidate] === name);
    if (key === undefined || status === null) return statusView('unset', '状态未知');
    return dependencyView(key, status.dependencies[key]);
  };

  const problemNextStep = (name: string): string => {
    if (name === '本地服务') return '请确认 Stratide 已在后台运行，然后重新读取。';
    if (name === '后台任务') return '请重新启动 Stratide；如果仍然出现，请查看诊断信息。';
    const key = DEPENDENCY_ORDER.find((candidate) => DEPENDENCY_LABELS[candidate] === name);
    return key === undefined ? '请查看诊断信息。' : DEPENDENCY_NEXT_STEP[key];
  };

  const diagnosticsData = {
    generated_at: formatDateTime(new Date().toISOString()),
    ui: { version: __UI_VERSION__, build: __BUILD_SHA__ },
    route: window.location.hash === '' ? '#overview' : window.location.hash,
    theme,
    browser: {
      user_agent: navigator.userAgent,
      viewport: window.innerWidth + 'x' + window.innerHeight,
    },
    runtime:
      status === null
        ? null
        : {
            managed: status.managed,
            product_version: status.product_version,
            build: status.build,
            repo_url: status.repo_url,
            issues_url: status.issues_url,
            port: status.port,
            setup_complete: status.setup_complete,
            config_error: status.config_error,
            service: { healthy: status.service.healthy, instance_id: status.service.instance_id },
            supervisor: {
              running: status.supervisor.running,
              status: status.supervisor.status,
              reason: status.supervisor.reason,
              pid: status.supervisor.pid,
              watch_running: status.supervisor.watch !== null,
            },
            dependencies: DEPENDENCY_ORDER.map((key) => ({
              key,
              state: status.dependencies[key].state,
              reason: status.dependencies[key].reason ?? null,
              version: status.dependencies[key].version ?? null,
            })),
            autostart: {
              exists: status.autostart.exists,
              enabled: status.autostart.enabled,
              mechanism: status.autostart.mechanism,
            },
            log_line_count: status.log_tail.length,
          },
    runtime_error: runtime.error === null ? null : runtime.error.code,
    health:
      health.data === null
        ? null
        : {
            service: health.data.service,
            paper_only: health.data.paper_only,
            market_data: health.data.market_data,
            forward_account: health.data.forward_account,
            agent: health.data.agent,
            notifications: health.data.notifications,
          },
    health_error: health.error === null ? null : health.error.code,
    snapshot:
      paper.meta === null
        ? null
        : {
            data_date: formatDay(paper.meta.last_day),
            first_day: formatDay(paper.meta.first_day),
            as_of: formatDay(paper.meta.as_of),
            last_valid_valuation_at:
              paper.meta.last_valid_valuation_at === null
                ? null
                : formatDateTime(paper.meta.last_valid_valuation_at),
            source: paper.meta.source,
            source_version: paper.meta.source_version,
            evidence_class: paper.meta.evidence_class,
            publication: paper.meta.publication,
            gap_count: paper.meta.gaps.length,
            snapshot_id: paper.meta.snapshot_id,
          },
    snapshot_read_error: paper.error === null ? null : paper.error.code,
    agent:
      agent.status === null
        ? { phase: agent.phase, error: agent.error === null ? null : agent.error.code }
        : {
            phase: agent.phase,
            paused: agent.status.paused,
            worker_error: agent.status.worker_error,
            worker_error_text: agent.status.worker_error_text,
            default_model: agent.status.default_model,
            eod_enabled: agent.status.eod.enabled,
            eod_latest_reason_text: agent.status.eod.latest === null ? null : agent.status.eod.latest.reason_text ?? null,
            budget: {
              state: agent.status.budget.state,
              currency: agent.status.budget.currency,
              daily_limit_micro: agent.status.budget.daily_limit_micro,
              monthly_limit_micro: agent.status.budget.monthly_limit_micro,
              daily_settled_micro: agent.status.budget.daily_settled_micro,
              monthly_settled_micro: agent.status.budget.monthly_settled_micro,
              reserved_micro: agent.status.budget.reserved_micro,
            },
            task_count: agent.tasks.length,
            error: agent.error === null ? null : agent.error.code,
          },
    wsl_probe: wslProbe === null ? null : { state: wslProbe.state, reason: wslProbe.reason },
    last_action_error: actionError,
  };
  const copyText = JSON.stringify(diagnosticsData, null, 2);

  const backfillRunning = runtime.market !== null && runtime.market.backfillRunning;
  const backfillComplete = runtime.market !== null && runtime.market.backfillComplete;
  const backfillTarget = runtime.market === null ? BACKFILL_TARGET : runtime.market.targetSessions;
  const sessionsReady = runtime.market === null ? 0 : runtime.market.sessionsReady;
  const displayRemaining =
    runtime.market === null
      ? 0
      : runtime.market.remaining > 0
        ? runtime.market.remaining
        : backfillComplete
          ? 0
          : runtime.market.gaps;
  const backfillDone = backfillComplete && sessionsReady > 0;

  const renderSections = (current: RuntimeStatus) => {
    const criticalReady = CRITICAL_DEPENDENCIES.every(
      (key) => dependencyStatusView(key, current.dependencies[key].state, null, null).kind === 'ok',
    );
    const setupReady = current.setup_complete && criticalReady;
    const marketInitialized = current.dependencies.market_eod.state === 'INITIALIZED';
    const tushareConfigured = current.dependencies.tushare_credential.state === 'CONFIGURED';
    const service = serviceView(health);
    const supervisor = supervisorView(current.supervisor);
    const collector = collectorView(current, backfillRunning);
    const backfillView: StatusView = !marketInitialized
      ? statusView('attention', '需要处理', '请先完成行情采集初始化')
      : runtime.market === null
        ? statusView('progress', '正在读取')
        : backfillRunning
          ? statusView('progress', '进行中', '待补齐 ' + displayRemaining + ' 个交易日（目标 ' + backfillTarget + ' 个交易日）')
          : backfillDone
            ? statusView('ok', '已完成', '历史行情已就绪（' + sessionsReady + ' 个交易日）')
            : sessionsReady === 0
              ? statusView('unset', '尚未开始', '尚未补录（目标 ' + backfillTarget + ' 个交易日）')
              : statusView('unset', '尚未完成', '待补齐 ' + displayRemaining + ' 个交易日（目标 ' + backfillTarget + ' 个交易日）');
    const backfillTotal = sessionsReady + displayRemaining;
    const progressValue =
      backfillDone ? 100 : backfillTotal === 0 ? 0 : Math.min(100, (sessionsReady / backfillTotal) * 100);
    const backfillDisabled = busy !== null || backfillRunning || !marketInitialized;

    const setupContent = (
      <div className="setup-body">
        {current.setup_complete && !criticalReady ? (
          <Callout tone="warning" title="首次设置已标记完成，但还有组件需要处理">
            请先处理“依赖检查”中需要处理的项；处理完成后这里会自动折叠。
          </Callout>
        ) : null}
        <div className="setup-token">
          <Field
            label="Tushare 访问令牌"
            htmlFor="runtime-tushare-token"
            hint="令牌只保存在本机，页面不会回显。"
          >
            <TextInput
              id="runtime-tushare-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={secret}
              placeholder={tushareConfigured ? '已设置；输入可覆盖' : '粘贴 Tushare 访问令牌'}
              onChange={(event) => setSecret(event.target.value)}
              data-testid="tushare-token"
            />
          </Field>
          <Button
            variant="secondary"
            disabled={secret.length === 0 || busy !== null}
            loading={busy === 'tushare'}
            data-testid="save-tushare-token"
            onClick={() => {
              void act('tushare', 'tushare-token', { token: secret }, '访问令牌已保存').then((ok) => {
                if (ok) setSecret('');
              });
            }}
          >
            保存令牌
          </Button>
        </div>
        <div className="setup-complete-row">
          <div>
            <strong>完成首次设置</strong>
            <p>{current.setup_complete ? '双击桌面图标会直接打开总览。' : '完成后，双击桌面图标会直接打开总览。'}</p>
            {current.setup_complete ? (
              <p className="setup-note">撤销后，双击桌面图标会重新打开设置页；账户、研究、预算与行情数据不受影响。</p>
            ) : null}
          </div>
          {current.setup_complete ? (
            <div className="setup-complete-actions">
              <StatusBadge status={statusView('ok', '已完成')} />
              <Button
                size="sm"
                variant="ghost"
                disabled={busy !== null}
                loading={busy === 'setup-undo'}
                onClick={() => setConfirm('setup-undo')}
                data-testid="setup-undo"
              >
                撤销完成标记
              </Button>
            </div>
          ) : (
            <Button
              variant="primary"
              disabled={busy !== null}
              onClick={() => setConfirm('setup')}
              data-testid="setup-complete"
            >
              完成设置
            </Button>
          )}
        </div>
        {current.setup_complete ? null : (
          <p className="setup-note">
            {criticalReady ? '关键组件已就绪，可以完成首次设置。' : '关键组件尚未全部就绪；现在标记完成后，本块会保持展开直到组件都正常。'}
          </p>
        )}
      </div>
    );

    return (
      <>
        <section className="runtime-section">
          <h2 className="card__title">依赖检查</h2>
          <ul className="runtime-deps" data-testid="dependency-list">
            {DEPENDENCY_ORDER.map((key) => {
              const view = dependencyView(key, current.dependencies[key]);
              return (
                <li key={key} className="runtime-dep" data-testid="dependency-row" data-state={view.kind}>
                  <span className="runtime-dep__name">{dependencyLabel(key)}</span>
                  <StatusBadge status={view} size="sm" />
                  <span className="runtime-dep__reason">{view.reason ?? '—'}</span>
                </li>
              );
            })}
          </ul>
          <details className="runtime-advanced" data-testid="local-engine-settings">
            <summary>本地预测引擎（WSL）设置</summary>
            <div className="runtime-advanced__body">
              <div className="runtime-actions">
                <Button size="sm" variant="secondary" disabled={busy !== null} loading={busy === 'detect'} onClick={() => void detectWsl()}>
                  自动检测
                </Button>
                <Button size="sm" variant="secondary" disabled={busy !== null} loading={busy === 'probe'} onClick={() => void probeWsl()}>
                  检查状态
                </Button>
              </div>
              <div className="runtime-form">
                <Field label="WSL 发行版" htmlFor="wsl-distribution">
                  <TextInput
                    id="wsl-distribution"
                    value={wslForm.distribution}
                    placeholder="例如 Ubuntu-24.04"
                    onChange={(event) => setWslForm({ ...wslForm, distribution: event.target.value })}
                  />
                </Field>
                <Field label="工作树路径" htmlFor="wsl-workspace">
                  <TextInput
                    id="wsl-workspace"
                    value={wslForm.workspace}
                    placeholder="WSL 内的项目目录"
                    onChange={(event) => setWslForm({ ...wslForm, workspace: event.target.value })}
                  />
                </Field>
                <Field label="Python 路径" htmlFor="wsl-python">
                  <TextInput
                    id="wsl-python"
                    value={wslForm.python}
                    placeholder=".venv/bin/python"
                    onChange={(event) => setWslForm({ ...wslForm, python: event.target.value })}
                  />
                </Field>
                <Field label="模型目录" htmlFor="wsl-model">
                  <TextInput
                    id="wsl-model"
                    value={wslForm.model}
                    placeholder="本地预测模型目录"
                    onChange={(event) => setWslForm({ ...wslForm, model: event.target.value })}
                  />
                </Field>
              </div>
              <div className="runtime-actions">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy !== null}
                  loading={busy === 'wsl'}
                  onClick={() =>
                    void act(
                      'wsl',
                      'wsl',
                      { ...wslForm },
                      '本地预测引擎设置已保存',
                      probeWsl,
                    )
                  }
                >
                  保存设置
                </Button>
              </div>
            </div>
          </details>
        </section>

        {setupReady ? (
          <section className="runtime-section">
            <details className="runtime-advanced" data-testid="setup-block">
              <summary>首次设置 · 已完成</summary>
              {setupContent}
            </details>
          </section>
        ) : (
          <section className="runtime-section" data-testid="setup-block">
            <h2 className="card__title">首次设置</h2>
            {setupContent}
          </section>
        )}

        <section className="runtime-section">
          <h2 className="card__title">历史补录</h2>
          <div className="backfill">
            <div className="backfill__head">
              <StatusBadge status={backfillView} />
              <span className="backfill__count" data-testid="backfill-progress">
                {backfillView.reason ?? '—'}
              </span>
            </div>
            <ProgressBar value={progressValue} label="历史补录进度" />
            <div className="backfill__meta">
              {runtime.market !== null && runtime.market.lastSuccessfulDate !== null ? (
                <span>最近更新：{formatDay(runtime.market.lastSuccessfulDate)}</span>
              ) : null}

            </div>
            <div className="runtime-actions">
              <Button
                size="sm"
                variant="secondary"
                disabled={backfillDisabled}
                loading={busy === 'backfill'}
                onClick={backfillDone ? () => setConfirm('backfill') : startBackfill}
                data-testid={backfillDone ? 'backfill-restart' : 'backfill-start'}
              >
                {backfillRunning ? '补录进行中' : backfillDone ? '重新补录' : '开始补录'}
              </Button>
            </div>
          </div>
        </section>

        <section className="runtime-section">
          <h2 className="card__title">后台任务</h2>
          <div className="runtime-rows">
            <div className="runtime-row">
              <span className="runtime-row__label">本地服务</span>
              <span className="runtime-row__value">
                <StatusBadge status={service} size="sm" />
                <span className="runtime-row__reason">{service.reason ?? ''}</span>
              </span>
            </div>
            <div className="runtime-row">
              <span className="runtime-row__label">后台任务</span>
              <span className="runtime-row__value">
                <StatusBadge status={supervisor} size="sm" />
                <span className="runtime-row__reason">{supervisor.reason ?? ''}</span>
              </span>
            </div>
            <div className="runtime-row">
              <span className="runtime-row__label">行情自动采集</span>
              <span className="runtime-row__value">
                <StatusBadge status={collector} size="sm" />
                <span className="runtime-row__reason">{collector.reason ?? ''}</span>
              </span>
            </div>
            <div className="runtime-row" data-testid="autostart-row">
              <span className="runtime-row__label">登录 Windows 后自动启动后台</span>
              <Switch
                label="登录 Windows 后自动启动后台"
                checked={current.autostart.enabled}
                busy={busy === 'autostart'}
                disabled={busy !== null}
                onChange={(checked) =>
                  void act('autostart', 'autostart', { enabled: checked }, checked ? '已开启登录自启' : '已关闭登录自启')
                }
              />
            </div>
            <div className="runtime-row">
              <span className="runtime-row__label">版本与更新</span>
              <VersionCheck version={current.product_version} build={current.build} />
            </div>
          </div>
          <details className="runtime-advanced">
            <summary>高级</summary>
            <div className="runtime-advanced__body">
              <div className="runtime-actions">
                <Button size="sm" variant="ghost" icon="database" onClick={() => openFolder('data')}>
                  打开数据目录
                </Button>
                <Button size="sm" variant="ghost" icon="file" onClick={() => openFolder('logs')}>
                  打开日志目录
                </Button>
              </div>
            </div>
          </details>
        </section>

        <section className="runtime-section">
          <details className="runtime-advanced" data-testid="recent-logs">
            <summary>最近后台日志</summary>
            <div className="runtime-advanced__body">
              {current.log_tail.length === 0 ? (
                <p className="runtime-log__empty">暂无日志。</p>
              ) : (
                <pre className="runtime-log">{current.log_tail.map(logLineText).join('\n')}</pre>
              )}
              <div className="runtime-log__actions">
                <Button size="sm" variant="ghost" icon="file" onClick={() => openFolder('logs')}>
                  打开日志目录
                </Button>
              </div>
            </div>
          </details>
        </section>
      </>
    );
  };

  return (
    <CardBody className="runtime-panel">
      <section className="runtime-overall" data-testid="overall-status">
        <div className="runtime-overall__head">
          <div>
            <h2 className="card__title">整体状态</h2>
            <div className="runtime-overall__summary">
              <StatusBadge status={overall.status} />
              {overall.status.reason === undefined ? null : (
                <span className="runtime-overall__reason">{overall.status.reason}</span>
              )}
            </div>
          </div>
          <div className="runtime-overall__actions">
            <Button size="sm" icon="refresh" loading={runtime.checking} onClick={() => runtime.refresh()} data-testid="runtime-refresh">
              刷新
            </Button>
            <span data-testid="copy-diagnostics">
              <CopyButton text={copyText} label="复制诊断信息" />
            </span>
          </div>
        </div>
        <div className="runtime-overall__meta">
          <span>
            {overall.readyCount} / {overall.totalCount} 项正常
          </span>
          {checkedAtText === null ? null : <span>更新于 {checkedAtText}</span>}
        </div>
        {overall.problems.length === 0 ? null : (
          <div className="runtime-problems">
            {overall.problems.map((name) => {
              const view = problemView(name);
              return (
                <details key={name} className="runtime-problem" data-testid="overall-problem">
                  <summary className="runtime-problem__summary">
                    <span>{problemDisplayName(name)}</span>
                    <StatusBadge status={view} size="sm" />
                    <Icon name="chevron-down" size={14} className="runtime-problem__chevron" />
                  </summary>
                  <div className="runtime-problem__body">
                    <p>{view.reason ?? '原因未记录'}</p>
                    <p className="runtime-problem__next">{problemNextStep(name)}</p>
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>

      {runtime.error === null ? null : (
        <Callout tone="danger" title="无法读取系统状态" role="alert">
          {humanReasonText(runtime.error.code) ?? '失败，原因未记录'}
          {status === null ? '' : '；以下为上次成功读取的数据。'}
        </Callout>
      )}

      {status === null ? null : renderSections(status)}

      <Diagnostics title="诊断信息" data={diagnosticsData} />

      <Modal
        open={confirm === 'setup'}
        onClose={() => setConfirm(null)}
        eyebrow="首次设置"
        title="标记首次设置为已完成？"
        description="标记后，双击桌面图标会直接打开总览；之后可在本页撤销。"
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>取消</Button>
            <Button variant="primary" loading={busy === 'setup'} onClick={completeSetup}>
              完成设置
            </Button>
          </>
        }
      >
        <p>请确认 Tushare 访问令牌与行情采集已经设置好；如果还有组件需要处理，之后仍可在本页处理。</p>
      </Modal>

      <Modal
        open={confirm === 'setup-undo'}
        onClose={() => setConfirm(null)}
        eyebrow="首次设置"
        title="撤销“首次设置已完成”？"
        description="撤销后，双击桌面图标会重新打开设置页。"
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>取消</Button>
            <Button variant="primary" loading={busy === 'setup-undo'} onClick={undoSetup}>
              撤销完成标记
            </Button>
          </>
        }
      >
        <p>只删除“已完成”标记；模拟账户、研究任务、预算和行情数据不会改变。</p>
      </Modal>

      <Modal
        open={confirm === 'backfill'}
        onClose={() => setConfirm(null)}
        eyebrow="历史数据补齐"
        title="重新补录 84 个交易日？"
        description="系统会再次请求补齐最近 84 个交易日的行情。补齐期间行情采集会暂停，完成后自动恢复。"
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>取消</Button>
            <Button variant="primary" loading={busy === 'backfill'} onClick={startBackfill}>
              重新补录
            </Button>
          </>
        }
      >
        <p>补齐在后台进行，受数据源限速影响，可能需要较长时间；关闭页面不会中断。</p>
      </Modal>
    </CardBody>
  );
}
