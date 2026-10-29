import { useRef } from 'react';
import type { KeyboardEvent, ReactNode, Ref } from 'react';
import { Card, CardBody } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { Kv } from '../components/ui/Kv';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Icon } from '../icons';
import type { IconName } from '../icons';
import { formatDateTime, formatDay } from '../lib/format';
import { SETTINGS_SECTIONS, SETTINGS_SECTION_LABELS } from '../lib/route';
import type { SettingsSection } from '../lib/route';
import type { MotionPreference, ThemePreference } from '../lib/storage';
import type { PaperDataState } from '../state/usePaperData';
import type { HealthState } from '../state/useHealth';
import { useTheme } from '../state/ThemeProvider';
import { ModeBadge, EvidenceBadge } from '../components/domain/Badges';

const SECTION_ICONS: Record<SettingsSection, IconName> = {
  appearance: 'sun',
  data: 'database',
  security: 'shield',
  about: 'info',
};

const SECTION_DESCRIPTIONS: Record<SettingsSection, string> = {
  appearance: '主题与动效，只保存在当前浏览器。',
  data: '当前 Paper 快照的来源与日期范围。',
  security: '本机服务能做什么、不能做什么。',
  about: '版本、构建与界面技术。',
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
}: {
  paper: PaperDataState;
  health: HealthState;
  section: SettingsSection;
  onSection: (section: SettingsSection) => void;
  titleRef?: Ref<HTMLHeadingElement>;
}) {
  const { theme, motion, setTheme, setMotion } = useTheme();
  const meta = paper.meta;
  const gaps = Array.isArray(meta?.gaps) ? meta.gaps : [];
  const notificationStatusText = health.error ? '状态不可读' : health.data?.notifications ?? 'unknown';
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
    if (section === 'appearance') {
      return (
        <Card className="settings-card">
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
                <div className="settings-row__label">动效</div>
                <p className="settings-row__hint">跟随系统 prefers-reduced-motion，或在此强制减少。</p>
              </div>
              <SegmentedControl
                label="减少动效"
                value={motion}
                onChange={(value: MotionPreference) => setMotion(value)}
                options={[
                  { value: 'system', label: '跟随系统' },
                  { value: 'reduce', label: '减少动效' },
                ]}
                compact
              />
            </div>
          </CardBody>
        </Card>
      );
    }

    if (section === 'data') {
      return (
        <Card className="settings-card data-card">
          <CardBody>
            {paper.phase === 'loading' ? (
              <p className="muted">正在读取数据连接信息…</p>
            ) : meta ? (
              <>
                <Kv
                  items={[
                    { label: '账户快照', value: meta.snapshot_id },
                    { label: '来源', value: meta.source },
                    { label: '来源版本', value: meta.source_version },
                    {
                      label: '证据等级',
                      value: (
                        <span className="inline-row inline-row--tight">
                          <EvidenceBadge evidence={meta.evidence_class} />
                          <span className="mono">{meta.evidence_class}</span>
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
                    { label: '发布方式', value: meta.publication + ' · ' + meta.refresh_policy },
                    { label: '行情时效', value: meta.market_freshness },
                    { label: '前向账户', value: meta.forward_account },
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
                <p className="settings-note">更换报告需要重启本机服务；页面不会自动择新。</p>
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
        </Card>
      );
    }

    if (section === 'security') {
      return (
        <Card className="settings-card security-card">
          <CardBody>
            <div className="security-list">
              <SecurityRow icon="shield" title="Paper only">
                当前没有券商或实盘连接，账户数据来自启动时固定的只读报告快照。
              </SecurityRow>
              <SecurityRow icon="key" title="Owner 令牌仅内存">
                Agent 管理需要本机 owner-token；令牌不写入 localStorage、sessionStorage、URL 或控制台，刷新后失效。
              </SecurityRow>
              <SecurityRow icon="database" title="可信本机配置">
                模型、费率、预算与云授权由本机可信文件维护；Web 不提供加额、清锁或密钥读取。
              </SecurityRow>
              <SecurityRow icon="server" title="通知与审批">
                通知渠道：{notificationStatusText}。本页不伪造通知，也不提供审批写入。
              </SecurityRow>
            </div>
          </CardBody>
        </Card>
      );
    }

    return (
      <Card className="settings-card about-card">
        <CardBody>
          <Kv
            items={[
              { label: '前端版本', value: <span className="mono">{__UI_VERSION__}</span> },
              { label: '构建', value: <span className="mono">{__BUILD_SHA__ === 'local' ? 'local build' : __BUILD_SHA__}</span> },
              { label: 'Paper API', value: 'v1 · 只读同源' },
              { label: '后端', value: 'Rust stratided · 127.0.0.1' },
              { label: '静态资源', value: '本地 app.js / app.css，无 CDN、无遥测' },
              { label: '界面技术', value: 'React 19 + TypeScript + esbuild' },
            ]}
          />
          <div className="about-note">
            <Icon name="shield" size={15} />
            <span>金额以整数分、股数以整数股展示；未知值显示为 —。</span>
          </div>
        </CardBody>
      </Card>
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
        <div className="page-header__side">
          {meta ? <ModeBadge mode={meta.mode} /> : null}
          <Badge tone="outline">本机偏好</Badge>
        </div>
      </header>

      <div className="settings-page">
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
          <p className="settings-nav__meta">UI {__UI_VERSION__} · local</p>
        </div>

        <div
          className="settings-panel"
          role="tabpanel"
          id={'settings-panel-' + section}
          aria-labelledby={'settings-tab-' + section}
          tabIndex={0}
        >
          <div className="settings-panel__head">
            <h2 className="settings-panel__title">{SETTINGS_SECTION_LABELS[section]}</h2>
            <p className="settings-panel__desc">{SECTION_DESCRIPTIONS[section]}</p>
          </div>
          {panel}
        </div>
      </div>
    </>
  );
}
