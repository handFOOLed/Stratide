import { useRef } from 'react';
import type { KeyboardEvent, ReactNode, Ref } from 'react';
import { Card, CardBody } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { Kv } from '../components/ui/Kv';
import { Switch } from '../components/ui/Switch';
import { Icon } from '../icons';
import type { IconName } from '../icons';
import { formatDateTime, formatDay } from '../lib/format';
import { SETTINGS_SECTIONS, SETTINGS_SECTION_LABELS } from '../lib/route';
import type { SettingsSection } from '../lib/route';
import type { ThemePreference } from '../lib/storage';
import type { PaperDataState } from '../state/usePaperData';
import type { HealthState } from '../state/useHealth';
import { useTheme } from '../state/ThemeProvider';
import { EvidenceBadge } from '../components/domain/Badges';
import { TechnicalDetails } from '../components/domain/WorkspaceStudies';
import type { WorkspaceState } from '../lib/workspace';
import type { AgentState } from '../state/useAgent';
import { formatMicro } from '../lib/format';
import { MarketResearchPanel } from '../components/domain/MarketResearchPanel';
import { RuntimePanel } from '../components/domain/RuntimePanel';

const SECTION_ICONS: Record<SettingsSection, IconName> = {
  appearance: 'sun',
  runtime: 'server',
  data: 'database',
  security: 'shield',
  about: 'info',
};

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string; hint: string; preview: 'system' | 'light' | 'dark' }> = [
  { value: 'system', label: '跟随系统', hint: '根据系统深浅色自动切换', preview: 'system' },
  { value: 'light', label: '浅色', hint: '适合明亮环境', preview: 'light' },
  { value: 'dark', label: '深色', hint: '适合低光环境', preview: 'dark' },
];

function ThemePreview({ kind }: { kind: 'system' | 'light' | 'dark' }) {
  return (
    <span className={'theme-preview theme-preview--' + kind} aria-hidden="true">
      <span className="theme-preview__side" />
      <span className="theme-preview__main">
        <span className="theme-preview__bar theme-preview__bar--wide" />
        <span className="theme-preview__bar" />
        <span className="theme-preview__card" />
      </span>
    </span>
  );
}

function SecurityRow({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <div className="security-row">
      <span className="security-row__icon"><Icon name={icon} /></span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

export function SettingsPage({
  paper,
  health,
  section,
  onSection,
  titleRef,
  workspace,
  agent,
}: {
  paper: PaperDataState;
  health: HealthState;
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  titleRef?: Ref<HTMLHeadingElement>;
  workspace: WorkspaceState;
  agent: AgentState;
}) {
  const { theme, motion, setTheme, setMotion } = useTheme();
  const meta = paper.meta;
  const gaps = Array.isArray(meta?.gaps) ? meta.gaps : [];
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys = ['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    let next = index;
    if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = SETTINGS_SECTIONS.length - 1;
    else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % SETTINGS_SECTIONS.length;
    else next = (index - 1 + SETTINGS_SECTIONS.length) % SETTINGS_SECTIONS.length;
    const target = SETTINGS_SECTIONS[next];
    if (!target) return;
    onSection(target);
    window.requestAnimationFrame(() => tabRefs.current[target]?.focus());
  };

  const panel = (() => {
    if (section === 'runtime') {
      return <RuntimePanel />;
    }

    if (section === 'appearance') {
      return (
        <CardBody>
          <fieldset className="theme-fieldset">
            <legend className="field__label">主题</legend>
            <div className="theme-grid" role="radiogroup" aria-label="主题">
              {THEME_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className="theme-choice"
                  data-theme-choice={option.value}
                  data-checked={theme === option.value ? 'true' : undefined}
                >
                  <input
                    type="radio"
                    name="stratide-theme"
                    value={option.value}
                    checked={theme === option.value}
                    onChange={() => setTheme(option.value)}
                    className="visually-hidden"
                  />
                  <ThemePreview kind={option.preview} />
                  <span className="theme-choice__text">
                    <span className="theme-choice__label">
                      {option.label}
                      {theme === option.value ? <Icon name="check" size={13} /> : null}
                    </span>
                    <span className="theme-choice__hint">{option.hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="settings-row">
            <div className="settings-row__main">
              <div className="settings-row__label">减弱动态效果</div>
            </div>
            <Switch
              label="减弱动态效果"
              checked={motion === 'reduce'}
              onChange={(checked) => setMotion(checked ? 'reduce' : 'system')}
            />
          </div>
        </CardBody>
      );
    }

    if (section === 'data') {
      return (
        <CardBody className="data-card">
          <h2 className="card__title">来源、时效与完整性</h2>
          <p>历史 PIT 尚未验证；开盘流实收尚未验证。盘后 daily.open 仅支持前日冻结意图的事后 Paper 假设。</p>
          <p className="muted">Tushare 未复权日线：价格为元、成交量为手（100 股）、金额为千元；以实际取得时间记录来源，不推断历史首次发布时间。</p>
          {workspace.data!==null && workspace.data.admission!==undefined?<div className="mini-table-wrap"><table className="mini-table"><caption>真实数据资格清单</caption><thead><tr><th>待补证据</th><th>状态</th><th>任务</th></tr></thead><tbody>{workspace.data.admission.matrix.map(row=><tr key={row.dependency}><td>{row.required_evidence}</td><td>受阻</td><td>{row.issue}</td></tr>)}</tbody></table><TechnicalDetails value={workspace.data.admission}/></div>:null}
          {workspace.data !== null ? workspace.data.evidence.map(e=><div className="study-row" key={e.id}><strong>{e.name}</strong><p>已有本地来源记录；交易资格仍受原准入判定约束。</p><TechnicalDetails value={e}/></div>) : null}
          {paper.phase === 'loading' ? (
            <p className="muted">正在读取数据连接信息…</p>
          ) : meta ? (
            <>
              <Kv
                items={[
                  { label: '账户快照', value: meta.snapshot_id.slice(0,8)+'…'+meta.snapshot_id.slice(-6) },
                  { label: '来源', value: meta.source },
                  { label: '来源版本', value: meta.source_version },
                  {
                    label: '证据等级',
                    value: (
                      <span className="inline-row inline-row--tight">
                        <EvidenceBadge evidence={meta.evidence_class} />
                      </span>
                    ),
                  },
                  {
                    label: '报告区间',
                    value: formatDay(meta.first_day) + ' — ' + formatDay(meta.last_day) + ' · ' + String(meta.timezone ?? 'Asia/Shanghai'),
                  },
                  {
                    label: '最后有效估值',
                    value: meta.last_valid_valuation_at ? formatDateTime(meta.last_valid_valuation_at) : formatDay(meta.as_of),
                  },
                  { label: '发布方式', value: meta.publication==='authoritative_paper_ledger'?'原 Paper 账本，只读事务':'最后发布报告，更新需重启' },
                  { label: '行情时效', value: '仅盘后/快照，非实时' },
                  { label: '前向账户', value: '尚未验证前向成交' },
                  {
                    label: '未观察日历日',
                    value: String(meta.unobserved_calendar_days_including_weekends ?? '—'),
                  },
                  { label: '缺开盘证据段', value: String(meta.missing_opening_evidence_sessions ?? '—') },
                  { label: '未核验状态段', value: String(meta.unverified_status_sessions ?? '—') },
                  {
                    label: '记录缺口',
                    value: gaps.length
                      ? gaps
                          .map((gap) =>
                            typeof gap === 'string'
                              ? gap
                              : [gap.day ? formatDay(gap.day) : '', gap.reason ?? ''].filter(Boolean).join(' '),
                          )
                          .join(' · ')
                      : '无记录缺口',
                  },
                ]}
              />
              <details className="disclosure data-disclosure">
                <summary className="disclosure__summary">
                  <span>技术摘要与账本尾</span>
                  <Icon name="chevron-down" />
                </summary>
                <div className="disclosure__body">
                  <Kv
                    tight
                    items={[
                      { label: 'snapshot_id', value: <span className="code-chip code-chip--block">{meta.snapshot_id}</span> },
                      { label: 'report_sha256', value: <span className="code-chip code-chip--block">{meta.report_sha256}</span> },
                      { label: 'input_sha256', value: <span className="code-chip code-chip--block">{meta.input_sha256}</span> },
                      { label: 'ledger_head', value: <span className="code-chip code-chip--block">{meta.ledger_head}</span> },
                    ]}
                  />
                </div>
              </details>
              <p className="settings-note">更换报告需重启本机服务。</p>
            </>
          ) : (
            <EmptyState
              compact
              icon="database"
              title={paper.error?.code === 'NO_SNAPSHOT' ? '尚未选择 Paper 报告' : 'Paper 报告不可用'}
              description={paper.error?.message || '启动时通过 --report-dir 指定已发布报告目录。'}
              code={paper.error?.code}
            />
          )}
        </CardBody>
      );
    }

    if (section === 'security') {
      return (
        <CardBody className="security-card">
          <MarketResearchPanel token={agent.token} />
          <div className="security-list">
            <SecurityRow icon="shield" title="Paper 模式">
              只读报告快照，未连接券商或实盘账户。
            </SecurityRow>
            <SecurityRow icon="key" title="Owner 令牌仅内存">
              用于解锁 Agent 管理；刷新后失效，不写入浏览器存储或 URL。
            </SecurityRow>
            <SecurityRow icon="database" title="可信本机配置">
              模型、费率、预算和云授权由本机维护；Web 不提供加额、清锁或密钥读取。
            </SecurityRow>
            <SecurityRow icon="server" title="通知审批">
              {health.error ? '本地服务状态不可读。' : health.data!==null && health.data.notifications==='local_persistent_inbox'?'本机持久通知与研究审批可用；审批不提升预算、云外发或交易权限。':'尚未配置 Agent 控制服务；在本机启动时指定原 Agent 目录。'}
            </SecurityRow>
            <SecurityRow icon="database" title="Provider 与共享预算">
              {agent.status===null?'解锁 Agent 管理后查看原 Provider 与预算。':`日上限 ${formatMicro(agent.status.budget.daily_limit_micro,{currency:agent.status.budget.currency})}，月上限 ${formatMicro(agent.status.budget.monthly_limit_micro,{currency:agent.status.budget.currency})}。实际账单可能不同于估算。`}
              真实行情、TimesFM 风险及派生摘要默认拒绝外发；须在上方明确授权字段与范围。
            </SecurityRow>
          </div>
        </CardBody>
      );
    }

    return (
      <CardBody className="about-card">
        <Kv
          items={[
            { label: '前端版本', value: <span className="mono">{__UI_VERSION__}</span> },
            { label: '构建', value: <span className="mono">{__BUILD_SHA__ === 'local' ? 'local build' : __BUILD_SHA__}</span> },
            { label: 'Paper API', value: 'v1 · 只读同源' },
            { label: '后端', value: 'Rust stratided · 127.0.0.1' },
            { label: '静态资源', value: '本地 app.js / app.css，无 CDN、无遥测' },
            { label: '界面技术', value: 'React 19 + TypeScript + esbuild' },
            { label: '本地运行', value: 'Windows 11；按需复用 WSL2 TimesFM CPU' },
            { label: '备份与恢复', value: 'scripts/local-backup.py；先校验与 dry-run，恢复到新目录' },
            { label: '最近备份', value: workspace.data!==null && workspace.data.backup!==undefined && workspace.data.backup.state==='VERIFIED_LOCAL_BACKUP'?`完整性已核对，共 ${workspace.data.backup.files} 个文件`:'尚无已核对的备份清单；在本机配置指定备份 manifest' },
            { label: 'N100 部署', value: '已延后，不属于 V1 完成条件' },
          ]}
        />
      </CardBody>
    );
  })();

  return (
    <>
      <header className="page-header page-header--compact">
        <div className="page-header__main">
          <h1 className="page-title" ref={titleRef} tabIndex={-1}>
            设置
          </h1>
        </div>
      </header>

      <Card className="settings-page">
        <div className="settings-nav" role="tablist" aria-label="设置分类" aria-orientation="vertical">
          {SETTINGS_SECTIONS.map((item, index) => (
            <button
              key={item}
              type="button"
              role="tab"
              id={'settings-tab-' + item}
              aria-selected={section === item}
              aria-controls={'settings-panel-' + item}
              tabIndex={section === item ? 0 : -1}
              ref={(node) => {
                tabRefs.current[item] = node;
              }}
              className="settings-nav__item"
              onClick={() => onSection(item)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              <Icon name={SECTION_ICONS[item]} size={16} />
              {SETTINGS_SECTION_LABELS[item]}
            </button>
          ))}
        </div>

        <div
          className="settings-panel"
          role="tabpanel"
          id={'settings-panel-' + section}
          aria-labelledby={'settings-tab-' + section}
          tabIndex={0}
        >
          {panel}
        </div>
      </Card>
    </>
  );
}
