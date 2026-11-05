import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import type { BadgeTone } from '../ui/Badge';
import { Callout } from '../ui/Callout';
import { CardBody } from '../ui/Card';
import { Field, TextInput } from '../ui/Field';
import { Switch } from '../ui/Switch';
import { useToast } from '../ui/Toast';
import { formatDateTime } from '../../lib/format';
import {
  loadRuntimeStatus,
  runtimeAction,
  runtimeToken,
  shanghaiToday,
} from '../../lib/runtime';
import type { DependencyStatus, RuntimeStatus } from '../../lib/runtime';
import { ApiError } from '../../lib/api';

const REASONS: Record<string, string> = {
  OK: '后台服务与 EOD 调度正常。',
  STARTING: '正在启动本机服务…',
  DASHBOARD_STARTING: '服务进程已启动，等待健康检查。',
  DASHBOARD_EXITED: 'Dashboard 进程异常退出；后台会在退避后重试，日志保留。',
  DASHBOARD_START_FAILED: 'Dashboard 未能启动；请检查端口与安装文件。',
  EXTERNAL_STRATIDE_INSTANCE: '端口上已有一个非当前后台管理的 Stratide 实例；为避免第二个调度链，未启动 EOD watch。',
  PORT_IN_USE_BY_OTHER_APPLICATION: '端口已被其他程序占用；Stratide 不会误连或结束该进程。',
  EOD_NOT_CONFIGURED: '尚未初始化 EOD 行情采集；数据与 Paper 不会自动产生。',
  PYTHON_RUNTIME_MISSING: '未找到随安装包提供的 Python 运行时。',
  WATCH_EXITED: 'EOD watch 已退出；后台会退避重启并保留原 journal。',
  DASHBOARD_BINARY_MISSING: '安装目录缺少 stratided.exe。',
  STOPPED_BY_OWNER: '后台服务已由 Owner 停止。',
  STOPPED_WITH_UNMANAGED_SERVICE: '后台已停止，但检测到未受管理的实例仍在运行。',
};

const DEPENDENCIES: Array<[keyof RuntimeStatus['dependencies'], string]> = [
  ['python', 'Python 运行时'],
  ['wsl', 'WSL2'],
  ['timesfm', 'TimesFM CPU'],
  ['tushare_credential', 'Tushare 凭据'],
  ['market_eod', 'EOD 行情采集'],
  ['paper_account', 'Paper 账户'],
  ['agent', '研究 Agent'],
];

function tone(state: string): BadgeTone {
  if (['READY', 'CONFIGURED', 'INITIALIZED', 'COMPLETE', 'RUNNING'].includes(state)) return 'success';
  if (['MISSING', 'NOT_CONFIGURED', 'DEGRADED', 'EXTERNAL_WSL_WORKSPACE_REQUIRED'].includes(state)) return 'warning';
  if (state.startsWith('BLOCKED') || ['BROKEN', 'UNAVAILABLE', 'FAILED'].includes(state)) return 'danger';
  return 'neutral';
}

function label(value: DependencyStatus): string {
  if (value.state === 'CONFIGURED' && value.configured === false) return '未配置';
  const map: Record<string, string> = {
    READY: '可用',
    CONFIGURED: '已配置',
    INITIALIZED: '已初始化',
    COMPLETE: '已完成',
    MISSING: '未配置',
    NOT_CONFIGURED: '未配置',
    BROKEN: '不可用',
    UNAVAILABLE: '不可用',
    BLOCKED_MISSING_RUNTIME: '缺少运行时',
    EXTERNAL_WSL_WORKSPACE_REQUIRED: '需 WSL 工作树',
    BINDING_INVALID_OR_MISSING_LEDGER: '绑定无效',
    UNKNOWN: '未知',
  };
  return map[value.state] ?? value.state;
}

function explain(value: DependencyStatus): string {
  const parts: string[] = [];
  if (value.version) parts.push('v' + value.version);
  if (value.distributions && value.distributions.length > 0) parts.push(value.distributions.join(' / '));
  if (value.reason) parts.push(value.reason);
  if (value.note) parts.push(value.note);
  return parts.join(' · ');
}

export function RuntimePanel() {
  const { push } = useToast();
  const token = runtimeToken();
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [secret, setSecret] = useState('');
  const [startDate, setStartDate] = useState(shanghaiToday);
  const controller = useRef<AbortController | null>(null);

  const refresh = useCallback((silent = false) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    if (!silent) setLoading(true);
    loadRuntimeStatus(current.signal)
      .then((value) => {
        setStatus(value);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.code === 'ABORTED') return;
        setError(caught instanceof ApiError ? caught.code : 'RUNTIME_STATUS_FAILED');
      })
      .finally(() => {
        if (!current.signal.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => refresh(true), 15_000);
    return () => {
      window.clearInterval(timer);
      controller.current?.abort();
    };
  }, [refresh]);

  const act = async (name: string, path: string, body: Record<string, unknown>, success: string) => {
    setBusy(name);
    setError(null);
    try {
      await runtimeAction(path, body);
      push({ title: success, tone: 'success' });
      refresh(true);
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.code : 'RUNTIME_ACTION_FAILED';
      setError(code);
      push({ title: '操作未完成', description: code, tone: 'danger' });
    } finally {
      setBusy(null);
    }
  };

  if (!status && !error) {
    return <CardBody><p className="muted">正在读取本机运行状态…</p></CardBody>;
  }

  const supervisor = status?.supervisor;
  const reasonText = supervisor ? (REASONS[supervisor.reason] ?? supervisor.reason) : '—';

  return (
    <CardBody className="install-panel">
      {!token ? (
        <Callout tone="warning" title="只读诊断">
          本页的本机设置操作需要桌面临时令牌。双击桌面 Stratide 图标重新打开即可解锁；令牌只保存在本次页面内存。
        </Callout>
      ) : null}
      {error ? (
        <Callout tone="danger" title="运行状态不可读">
          <span className="mono">{error}</span>
        </Callout>
      ) : null}

      <div className="install-actions">
        <Button size="sm" icon="refresh" loading={loading} onClick={() => refresh()}>刷新状态</Button>
        <Button
          size="sm"
          icon="database"
          disabled={!token}
          onClick={() => act('data', 'open-folder', { target: 'data' }, '已打开数据目录')}
        >
          打开数据目录
        </Button>
        <Button
          size="sm"
          icon="file"
          disabled={!token}
          onClick={() => act('logs', 'open-folder', { target: 'logs' }, '已打开日志目录')}
        >
          打开日志目录
        </Button>
      </div>

      <section className="install-section">
        <h2 className="card__title">后台服务</h2>
        <div className="install-grid">
          <div className="install-item">
            <div className="install-item__head"><strong>本地服务</strong><Badge tone={status?.service.healthy ? 'success' : 'danger'}>{status?.service.healthy ? '在线' : '离线'}</Badge></div>
            <p className="muted">127.0.0.1:{status?.port ?? '—'} · 仅本机 · Paper-only</p>
            <p className="muted mono">{status?.service.instance_id ?? ''}</p>
          </div>
          <div className="install-item">
            <div className="install-item__head"><strong>后台 Supervisor</strong><Badge tone={tone(supervisor?.status ?? 'UNKNOWN')}>{supervisor?.status ?? '—'}</Badge></div>
            <p className="muted">{reasonText}</p>
            <p className="muted">PID {supervisor?.pid ?? '—'} · 更新 {supervisor?.updated_at ? formatDateTime(supervisor.updated_at) : '—'}</p>
          </div>
          <div className="install-item">
            <div className="install-item__head"><strong>EOD watch</strong><Badge tone={supervisor?.watch ? 'success' : 'warning'}>{supervisor?.watch ? '运行中' : '未运行'}</Badge></div>
            <p className="muted">PID {supervisor?.watch?.pid ?? '—'} · 重启 {supervisor?.watch?.restarts ?? 0} 次</p>
            <p className="muted">按 Asia/Shanghai 交易日；复用原 eod-operator market watch，不新建调度或账本。</p>
          </div>
          <div className="install-item">
            <div className="install-item__head"><strong>版本</strong><span className="mono">v{status?.product_version ?? '—'}</span></div>
            <p className="muted">安装目录：<span className="mono">{status?.app_dir ?? '—'}</span></p>
            <p className="muted">数据目录：<span className="mono">{status?.data_root ?? '—'}</span></p>
          </div>
        </div>
      </section>

      <section className="install-section">
        <h2 className="card__title">登录自启</h2>
        <div className="settings-row">
          <div className="settings-row__main">
            <div className="settings-row__label">Windows 用户登录后启动后台</div>
            <p className="muted">当前用户任务，非管理员服务；延迟 30 秒，不自动打开浏览器。关闭后不会再自启。</p>
          </div>
          <Switch
            label="登录自启"
            checked={status?.autostart.enabled ?? false}
            busy={busy === 'autostart'}
            disabled={!token || busy !== null}
            onChange={(checked) => act('autostart', 'autostart', { enabled: checked }, checked ? '已启用登录自启' : '已停用登录自启')}
          />
        </div>
        <p className="muted">
          任务名 <span className="mono">{status?.autostart.task_name ?? 'Stratide'}</span> · 机制{' '}
          {status?.autostart.mechanism === 'TASK_SCHEDULER'
            ? 'Task Scheduler 登录触发'
            : status?.autostart.mechanism === 'RUN_KEY'
              ? '当前用户 Run 键（回退）'
              : '未启用'}{' '}
          · {status?.autostart.detail ?? '—'}
        </p>
      </section>

      <section className="install-section">
        <h2 className="card__title">依赖与权限诊断</h2>
        <p className="muted">缺少依赖时保持 BLOCKED；安装包不会静默下载模型或代替 Owner 授权。</p>
        <div className="install-grid">
          {DEPENDENCIES.map(([key, name]) => {
            const value = status?.dependencies[key];
            return (
              <div className="install-item" key={key}>
                <div className="install-item__head">
                  <strong>{name}</strong>
                  <Badge tone={value ? tone(value.state) : 'neutral'}>{value ? label(value) : '—'}</Badge>
                </div>
                <p className="muted install-item__detail">{value ? explain(value) : '—'}</p>
              </div>
            );
          })}
        </div>
        <Callout tone="info" title="已存在的 Owner 设置仍是权威">
          DeepSeek 预算（¥5/日、¥100/月）、研究自动开关与真实行情外发授权，继续在“设置 → 权限与安全”的既有 Owner 流程中维护；此安装页不提升预算、不授予外发、不写入 Paper 本金或风险限额。
        </Callout>
      </section>

      <section className="install-section">
        <h2 className="card__title">首次设置</h2>
        <div className="install-setup">
          <div className="install-setup__row">
            <div>
              <strong>Tushare Token</strong>
              <p className="muted">只写入当前 Windows 用户凭据管理器，不回显、不写日志、不放进安装包。</p>
            </div>
            <div className="install-token-row">
              <Field label="Token" htmlFor="runtime-tushare-token">
                <TextInput
                  id="runtime-tushare-token"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={secret}
                  placeholder={status?.dependencies.tushare_credential.state === 'CONFIGURED' ? '已配置；输入可覆盖' : '粘贴 Tushare Token'}
                  disabled={!token}
                  onChange={(event) => setSecret(event.target.value)}
                />
              </Field>
              <Button
                variant="primary"
                disabled={!token || secret.length === 0 || busy !== null}
                loading={busy === 'tushare'}
                onClick={() => act('tushare', 'tushare-token', { token: secret }, 'Tushare Token 已保存').then(() => setSecret(''))}
              >
                保存
              </Button>
            </div>
          </div>

          <div className="install-setup__row">
            <div>
              <strong>EOD 行情采集</strong>
              <p className="muted">首次初始化不会立即拉取行情；启用后按上海交易日 16:10–18:00 窗口复用原 {status?.dependencies.market_eod.state === 'INITIALIZED' ? '已初始化' : '未初始化'} 数据仓库。</p>
            </div>
            <div className="install-token-row">
              <Field label="起始日期" htmlFor="runtime-start-date" hint="YYYYMMDD；不早于 16:00 的正式起点。">
                <TextInput
                  id="runtime-start-date"
                  value={startDate}
                  inputMode="numeric"
                  maxLength={8}
                  disabled={!token || status?.dependencies.market_eod.state === 'INITIALIZED'}
                  onChange={(event) => setStartDate(event.target.value.replace(/\D/g, '').slice(0, 8))}
                />
              </Field>
              <Button
                variant="secondary"
                disabled={!token || startDate.length !== 8 || busy !== null || status?.dependencies.market_eod.state === 'INITIALIZED'}
                loading={busy === 'init'}
                onClick={() => act('init', 'market', { action: 'init', start_date: startDate }, 'EOD 数据仓库已初始化')}
              >
                初始化
              </Button>
            </div>
            <div className="install-actions">
              <Button
                size="sm"
                variant="primary"
                disabled={!token || busy !== null || status?.dependencies.market_eod.state !== 'INITIALIZED'}
                loading={busy === 'enable'}
                onClick={() => act('enable', 'market', { action: 'enable' }, 'EOD 采集已启用')}
              >
                启用采集
              </Button>
              <Button
                size="sm"
                variant="danger"
                disabled={!token || busy !== null || status?.dependencies.market_eod.state !== 'INITIALIZED'}
                loading={busy === 'disable'}
                onClick={() => act('disable', 'market', { action: 'disable' }, 'EOD 采集已停用')}
              >
                安全停用采集
              </Button>
            </div>
          </div>

          <div className="install-setup__row">
            <div>
              <strong>完成安装引导</strong>
              <p className="muted">标记后，双击桌面图标会直接打开总览。Paper 本金/风险限额与真实行情外发仍需 Owner 按既有流程单独授权。</p>
            </div>
            <Button
              variant={status?.setup_complete ? 'secondary' : 'primary'}
              disabled={!token || busy !== null}
              loading={busy === 'setup'}
              onClick={() => act('setup', 'setup-complete', {}, '首次设置已标记完成')}
            >
              {status?.setup_complete ? '已标记完成' : '标记完成'}
            </Button>
          </div>
        </div>
      </section>

      <section className="install-section">
        <h2 className="card__title">最近后台日志</h2>
        <pre className="install-log">{status?.log_tail.length ? status.log_tail.join('\n') : '暂无日志。'}</pre>
      </section>
    </CardBody>
  );
}