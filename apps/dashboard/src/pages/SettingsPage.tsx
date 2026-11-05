import { useRef } from 'react';
import type { KeyboardEvent, Ref } from 'react';
import { Card, CardBody } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { Diagnostics } from '../components/ui/Diagnostics';
import type { DiagnosticItem } from '../components/ui/Diagnostics';
import { EmptyState } from '../components/ui/EmptyState';
import { Switch } from '../components/ui/Switch';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Icon } from '../icons';
import type { IconName } from '../icons';
import { countText, formatDateTime, formatDay } from '../lib/format';
import { SETTINGS_SECTION_LABELS } from '../lib/route';
import type { SettingsSection } from '../lib/route';
import type { ThemePreference } from '../lib/storage';
import { dataStatusView, humanReasonText } from '../lib/status';
import { TERMS } from '../lib/copy';
import type { PaperDataState } from '../state/usePaperData';
import type { HealthState } from '../state/useHealth';
import { useTheme } from '../state/ThemeProvider';
import { EvidenceBadge } from '../components/domain/Badges';
import { ProviderPanel } from '../components/domain/ProviderPanel';
import { RuntimePanel, VersionCheck } from '../components/domain/RuntimePanel';
import type { RuntimeState } from '../state/useRuntime';
import type { WorkspaceState } from '../lib/workspace';
import type { AgentState } from '../state/useAgent';

const SECTION_ICONS: Record<SettingsSection, IconName> = {
  appearance: 'sun',
  ai: 'key',
  data: 'database',
  runtime: 'server',
  about: 'info',
};

/** 设置分类的展示顺序：外观 → AI 服务与预算 → 数据与行情 → 系统与诊断 → 关于。 */
const SECTION_ORDER: readonly SettingsSection[] = ['appearance', 'ai', 'data', 'runtime', 'about'];

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string; hint: string; preview: 'system' | 'light' | 'dark' }> = [
  { value: 'system', label: '跟随系统', hint: '根据系统深浅色自动切换', preview: 'system' },
  { value: 'light', label: '浅色', hint: '适合明亮环境', preview: 'light' },
  { value: 'dark', label: '深色', hint: '适合低光环境', preview: 'dark' },
];

/** 数据质量详情里的技术口径：只在折叠的诊断区展示。 */
const PUBLICATION_LABELS: Record<string, string> = {
  last_published_snapshot: '最后发布的报告',
  authoritative_paper_ledger: '模拟账户账本（只读）',
};

const REFRESH_POLICY_LABELS: Record<string, string> = {
  explicit_process_restart: '重启本机服务后更新',
  read_only_latest_transaction: '随账本只读更新',
};

const MARKET_FRESHNESS_LABELS: Record<string, string> = {
  snapshot_only_not_live: '盘后快照，不是实时行情',
  eod_assumption_not_live: '盘后模拟假设，不是实时行情',
};

const FORWARD_ACCOUNT_LABELS: Record<string, string> = {
  not_available: '尚未启用',
  not_verified: '尚未验证',
};

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

function gapText(gaps: Array<string | { day?: string; reason?: string }>): string {
  if (gaps.length === 0) return '无';
  return gaps
    .map((gap) => {
      if (typeof gap === 'string') return gap;
      return [gap.day === undefined ? '' : formatDay(gap.day), gap.reason ?? ''].filter(Boolean).join(' ');
    })
    .join(' · ');
}

export function SettingsPage({
  paper,
  health,
  runtime,
  section,
  onSection,
  titleRef,
  workspace,
  agent,
}: {
  paper: PaperDataState;
  health: HealthState;
  runtime: RuntimeState;
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  titleRef?: Ref<HTMLHeadingElement>;
  workspace: WorkspaceState;
  agent: AgentState;
}) {
  const { theme, motion, setTheme, setMotion } = useTheme();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys = ['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    let next = index;
    if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = SECTION_ORDER.length - 1;
    else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % SECTION_ORDER.length;
    else next = (index - 1 + SECTION_ORDER.length) % SECTION_ORDER.length;
    const target = SECTION_ORDER[next];
    onSection(target);
    window.requestAnimationFrame(() => tabRefs.current[target]?.focus());
  };

  const panel = (() => {
    if (section === 'ai') {
      return (
        <CardBody className="settings-ai">
          <ProviderPanel agent={agent} />
          <p className="settings-note">研究预算可在本页修改；保存后会同步到 AI 研究页与任务预算校验。</p>
          <Diagnostics
            title="AI 服务诊断信息"
            data={{
              phase: agent.phase,
              error: agent.error === null ? null : { code: agent.error.code, message: agent.error.message },
              status: agent.status,
            }}
          />
        </CardBody>
      );
    }

    if (section === 'runtime') {
      return <RuntimePanel health={health} runtime={runtime} paper={paper} agent={agent} />;
    }

    if (section === 'appearance') {
      return (
        <CardBody className="settings-appearance">
          <fieldset className="theme-fieldset">
            <legend className="field__label">主题</legend>
            <div className="theme-grid" role="radiogroup" aria-label="主题">
              {THEME_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className="theme-choice"
                  data-theme-choice={option.value}
                  data-checked={theme === option.value ? 'true' : undefined}
                  data-testid="theme-choice"
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
          <div className="settings-row" data-testid="reduce-motion">
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
      const meta = paper.meta;
      const gaps = meta === null ? [] : meta.gaps;
      const status = dataStatusView({
        meta,
        errorCode: paper.error === null ? null : paper.error.code,
        errorMessage: paper.error === null ? null : paper.error.message,
        gaps: gaps.length,
      });
      const qualityItems: DiagnosticItem[] =
        meta === null
          ? []
          : [
              { label: '账户快照', value: meta.snapshot_id },
              { label: '来源', value: meta.source },
              { label: '来源版本', value: meta.source_version },
              { label: '证据等级', value: <EvidenceBadge evidence={meta.evidence_class} /> },
              { label: '数据日期', value: formatDay(meta.last_day) },
              {
                label: '报告区间',
                value: formatDay(meta.first_day) + ' — ' + formatDay(meta.last_day) + ' · 北京时间',
              },
              {
                label: '最后有效估值',
                value:
                  meta.last_valid_valuation_at === null
                    ? formatDay(meta.as_of)
                    : formatDateTime(meta.last_valid_valuation_at),
              },
              { label: '最后有效估值日', value: formatDay(meta.as_of) },
              { label: '发布方式', value: PUBLICATION_LABELS[meta.publication] ?? '—' },
              { label: '更新方式', value: REFRESH_POLICY_LABELS[meta.refresh_policy] ?? '—' },
              { label: '行情时效', value: MARKET_FRESHNESS_LABELS[meta.market_freshness] ?? '—' },
              { label: '前向账户', value: FORWARD_ACCOUNT_LABELS[meta.forward_account] ?? '—' },
              { label: '未观察日历日', value: countText(meta.unobserved_calendar_days_including_weekends, '天') },
              { label: '缺开盘证据段', value: countText(meta.missing_opening_evidence_sessions, '段') },
              { label: '未核验状态段', value: countText(meta.unverified_status_sessions, '段') },
              { label: '记录缺口', value: gapText(gaps) },
            ];
      return (
        <CardBody className="data-card">
          <div className="settings-data" data-testid="data-section">
            <h2 className="card__title">数据来源与更新</h2>
            <ul className="data-facts" data-testid="data-facts">
              <li>数据来源：Tushare 盘后行情。</li>
              <li>更新频率：每个交易日收盘后更新，不是实时行情。</li>
              <li>模拟成交：通过{TERMS.tradeProtection}后，{TERMS.simulatedFill}。</li>
            </ul>
            <div className="data-status" data-testid="data-integrity-status">
              <span className="data-status__title">数据完整性</span>
              <StatusBadge status={status} />
              {status.reason === undefined ? null : <span className="data-status__reason">{status.reason}</span>}
              {meta === null ? null : (
                <span className="data-status__note" data-testid="data-date">
                  数据日期 {formatDay(meta.last_day)}
                </span>
              )}
              {meta !== null && meta.as_of !== null && meta.as_of !== meta.last_day ? (
                <span className="data-status__note">最后有效估值日 {formatDay(meta.as_of)}</span>
              ) : null}
              {paper.loadedAt === null ? null : (
                <span className="data-status__note">更新于 {formatDateTime(new Date(paper.loadedAt).toISOString())}</span>
              )}
            </div>
            {paper.stale && paper.error !== null ? (
              <Callout tone="warning" title="最近一次读取失败，以下为上次成功的数据">
                {humanReasonText(paper.error.code) ?? '失败，原因未记录'}
              </Callout>
            ) : null}
            {paper.phase === 'error' && meta === null ? (
              <div className="data-empty">
                <EmptyState
                  compact
                  tone={status.kind === 'error' ? 'error' : 'neutral'}
                  icon="database"
                  title={status.kind === 'error' ? '数据读取失败' : '尚未设置模拟账户数据'}
                  description={status.reason ?? '还没有可用的模拟账户数据。'}
                  actions={
                    <Button size="sm" variant="secondary" icon="refresh" onClick={paper.refresh}>
                      重新读取
                    </Button>
                  }
                />
              </div>
            ) : null}
            {meta === null && paper.error === null ? (
              <p className="muted">正在读取数据状态…</p>
            ) : null}
            {meta === null && paper.error === null ? null : (
              <div data-testid="data-quality-details">
                <Diagnostics
                  title="数据质量详情"
                  items={qualityItems}
                  data={{
                    read_error:
                      paper.error === null
                        ? null
                        : { code: paper.error.code, message: paper.error.message, status: paper.error.status },
                    snapshot: meta,
                    research_data:
                      workspace.data === null
                        ? null
                        : {
                            state: workspace.data.state,
                            admission: workspace.data.admission ?? null,
                            evidence: workspace.data.evidence,
                            backup: workspace.data.backup ?? null,
                          },
                  }}
                />
              </div>
            )}
          </div>
        </CardBody>
      );
    }

    return (
      <CardBody className="about-card">
        <div className="about-version" data-testid="about-version">
          <h2 className="card__title">Stratide</h2>
          <VersionCheck
            version={runtime.status === null ? __UI_VERSION__ : runtime.status.product_version}
            uiVersion={__UI_VERSION__}
            build={runtime.status === null ? null : runtime.status.build}
          />
        </div>
        <div className="about-links">
          <a
            className="about-link"
            href={runtime.status?.issues_url ?? 'https://github.com/handFOOLed/Stratide/issues'}
            target="_blank"
            rel="noreferrer"
            data-testid="feedback-link"
          >
            <Icon name="arrow-up-right" size={14} />
            问题反馈与建议
          </a>
        </div>
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
        <div className="settings-nav" role="tablist" aria-label="设置分类" aria-orientation="vertical" data-testid="settings-nav">
          {SECTION_ORDER.map((item, index) => (
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
              data-testid={'settings-nav-' + item}
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
          data-testid="settings-panel"
        >
          {panel}
        </div>
      </Card>
    </>
  );
}
