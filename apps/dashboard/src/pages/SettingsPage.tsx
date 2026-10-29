import type { ReactNode, Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { Kv } from '../components/ui/Kv';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Icon } from '../icons';
import { formatDateTime, formatDay } from '../lib/format';
import type { MotionPreference, ThemePreference } from '../lib/storage';
import type { PaperDataState } from '../state/usePaperData';
import type { HealthState } from '../state/useHealth';
import { useTheme } from '../state/ThemeProvider';
import { ModeBadge, EvidenceBadge } from '../components/domain/Badges';

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

function SecurityRow({ icon, title, children }: { icon: 'shield' | 'key' | 'database' | 'server'; title: string; children: ReactNode }) {
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
  titleRef,
}: {
  paper: PaperDataState;
  health: HealthState;
  titleRef?: Ref<HTMLHeadingElement>;
}) {
  const { theme, motion, setTheme, setMotion } = useTheme();
  const meta = paper.meta;
  const gaps = Array.isArray(meta?.gaps) ? meta.gaps : [];
  const notImplemented = health.data?.notifications ?? null;
  const notificationStatusText = health.error ? '状态不可读' : notImplemented ?? 'unknown';

  return (
    <>
      <PageHeader
        eyebrow="Preferences"
        title="设置"
        description="外观、数据连接与本机权限边界。这里不复制账户或研究仪表盘，也不提供预算、密钥或交易写入。"
        titleRef={titleRef}
        side={<Badge tone="outline">本机偏好</Badge>}
      />

      <div className="grid settings-grid">
        <div className="col-7">
          <Card className="settings-card">
            <CardHead title="外观" subtitle="选择保存在当前浏览器的 localStorage；不包含令牌或财务数据。" />
            <CardBody>
              <fieldset className="theme-fieldset">
                <legend className="field__label">主题</legend>
                <div className="theme-grid" role="radiogroup" aria-label="主题">
                  {THEME_OPTIONS.map((option) => (
                    <label
                      key={option.value}
                      className="theme-choice"
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
                <div>
                  <div className="field__label">动效</div>
                  <p className="field__hint">跟随系统 prefers-reduced-motion，或在此强制减少。</p>
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
        </div>

        <div className="col-5">
          <Card className="settings-card security-card">
            <CardHead title="本机权限边界" subtitle="Web 只能读取已授权数据，不能扩大权限" />
            <CardBody>
              <div className="security-list">
                <SecurityRow icon="shield" title="Paper only">
                  当前没有券商或实盘连接。账户数据来自启动时固定的只读六报告快照。
                </SecurityRow>
                <SecurityRow icon="key" title="Owner 令牌仅内存">
                  Agent 管理需本机 owner-token；令牌不写入 localStorage、sessionStorage、URL 或控制台，刷新后失效。
                </SecurityRow>
                <SecurityRow icon="database" title="可信本机配置">
                  模型、费率、预算与云授权由本机可信文件/环境变量维护。Web 不提供加额、清锁或密钥读取。
                </SecurityRow>
                <SecurityRow icon="server" title="通知与审批">
                  通知渠道：{notificationStatusText}。本页不伪造通知，也不提供审批写入。
                </SecurityRow>
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="col-7">
          <Card className="settings-card data-card">
            <CardHead
              title="数据连接"
              subtitle="启动时固定一份已发布六报告快照；更新需以同一明确目录重启服务"
              actions={meta ? <ModeBadge mode={meta.mode} /> : <Badge tone="warning">未加载</Badge>}
            />
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
                      { label: '证据等级', value: <span className="inline-row inline-row--tight"><EvidenceBadge evidence={meta.evidence_class} /><span className="mono">{meta.evidence_class}</span></span> },
                      { label: '报告区间', value: formatDay(meta.first_day) + ' — ' + formatDay(meta.last_day) + ' · ' + String(meta.timezone ?? 'Asia/Shanghai') },
                      { label: '最后有效估值', value: meta.last_valid_valuation_at ? formatDateTime(meta.last_valid_valuation_at) : formatDay(meta.as_of) },
                      { label: '发布方式', value: meta.publication + ' · ' + meta.refresh_policy },
                      { label: '行情时效', value: meta.market_freshness },
                      { label: '前向账户', value: meta.forward_account },
                      { label: '验证范围', value: meta.validation },
                      { label: '未观察日历日', value: String(meta.unobserved_calendar_days_including_weekends ?? '—') + '（含周末，不能称为丢失交易日）' },
                      { label: '缺开盘证据段', value: String(meta.missing_opening_evidence_sessions ?? '—') },
                      { label: '未核验状态段', value: String(meta.unverified_status_sessions ?? '—') },
                      {
                        label: '记录缺口',
                        value: gaps.length
                          ? gaps
                              .map((gap) =>
                                typeof gap === 'string'
                                  ? gap
                                  : [gap.day ? formatDay(gap.day) : '', gap.reason ?? '']
                                      .filter(Boolean)
                                      .join(' '),
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
                  <p className="settings-note">页面使用右上角服务状态菜单重新读取。更换报告或发布新内容后，需要显式重启服务；没有目录监视或自动择新。</p>
                </>
              ) : (
                <EmptyState
                  compact
                  icon="database"
                  title={paper.error?.code === 'NO_SNAPSHOT' ? '尚未选择 Paper 报告' : 'Paper 报告不可用'}
                  description={
                    paper.error?.message ||
                    '启动时通过 --report-dir 指定已发布六报告目录。没有默认资金或默认测试账户。'
                  }
                  code={paper.error?.code}
                />
              )}
            </CardBody>
          </Card>
        </div>

        <div className="col-5">
          <Card className="settings-card about-card">
            <CardHead title="关于" subtitle="本地只读工作空间" actions={<Badge tone="outline">UI {__UI_VERSION__}</Badge>} />
            <CardBody>
              <Kv
                items={[
                  { label: '前端版本', value: <span className="mono">{__UI_VERSION__}</span> },
                  { label: '构建', value: <span className="mono">{__BUILD_SHA__ === 'local' ? 'local build' : __BUILD_SHA__}</span> },
                  { label: 'Paper API', value: 'v1 · 只读同源' },
                  { label: '后端', value: 'Rust stratided · 127.0.0.1' },
                  { label: '静态资源', value: '本地 app.js / app.css，无 CDN、无遥测、无外部字体请求' },
                  { label: '界面技术', value: 'React 19 + TypeScript + esbuild；共享组件与 CSS tokens' },
                ]}
              />
              <div className="about-note">
                <Icon name="shield" size={15} />
                <span>财务金额以整数分、股数以整数股展示；页面不会把未知值或历史收益伪装成实时结果。</span>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      <Callout tone="info" className="settings-footer-callout">
        本页只保存外观与动效偏好。账户、研究、预算与权限配置仍由本机可信服务维护；Web 不接受财务写入。
      </Callout>
    </>
  );
}