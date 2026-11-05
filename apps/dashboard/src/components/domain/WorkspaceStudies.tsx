import { Card, CardBody, CardHead } from '../ui/Card';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { EmptyState } from '../ui/EmptyState';
import { StatusBadge } from '../ui/StatusBadge';
import { Icon } from '../../icons';
import { EMPTY, TERMS, UNITS } from '../../lib/copy';
import { countText, formatDateTime, formatDay } from '../../lib/format';
import { failureReasonText, statusView } from '../../lib/status';
import type { StatusView } from '../../lib/status';
import type { Evaluation, Study, Workspace, WorkspaceState } from '../../lib/workspace';

const STUDY_KIND_TEXT: Record<string, string> = {
  'TimesFM CPU': '本地预测模型',
  'DeepSeek Fusion': 'AI 研究',
  '离线录制 Fusion': '离线研究记录',
};

function studyKindText(kind: string): string {
  return STUDY_KIND_TEXT[kind] ?? '研究报告';
}

function studyStatusView(state: string, reason: string | null): StatusView {
  switch (state) {
    case 'completed':
      return statusView('ok', '已完成');
    case 'running':
    case 'local_running':
      return statusView('progress', '运行中');
    case 'failed':
      return statusView('error', '运行失败', failureReasonText(reason));
    case 'BLOCKED':
      return statusView('attention', '已被阻止', failureReasonText(reason));
    case 'cancelled':
      return statusView('unset', '已取消');
    case 'FROZEN_NOT_RUN':
      return statusView('unset', '尚未运行');
    case 'verified_local_integrity':
      return statusView('ok', '正常');
    case 'NOT_BILLED':
      return statusView('unset', '无需计费');
    default:
      return statusView('unset', '状态未知');
  }
}

function candidateStatusView(state: string, reason: string | null): StatusView {
  switch (state) {
    case 'RESEARCH_ONLY':
      return statusView('unset', '仅供研究');
    case 'REGISTERED':
      return statusView('unset', '已登记');
    case 'FROZEN_CANDIDATE':
      return statusView('unset', '候选已冻结');
    case 'BLOCKED':
      return statusView('attention', '需要处理', failureReasonText(reason));
    default:
      return statusView('unset', '状态未知');
  }
}

function marketStatusView(state: string, reason: string | null): StatusView {
  switch (state) {
    case 'READY':
      return statusView('ok', '采集正常');
    case 'COMPLETE':
    case 'COMPLETED':
      return statusView('ok', '采集完成');
    case 'ALREADY_FROZEN':
      return statusView('ok', '今日已采集');
    case 'RUNNING':
      return statusView('progress', '正在采集');
    case 'WAITING_FOR_MARKET_CLOSE':
      return statusView('progress', '等待收盘');
    case 'PARTIAL':
      return statusView('attention', '采集不完整', failureReasonText(reason));
    case 'BLOCKED':
    case 'FAILED':
      return statusView('error', '采集失败', failureReasonText(reason));
    case 'MARKET_CLOSED':
      return statusView('unset', '今日休市');
    case 'NOT_CONFIGURED':
      return statusView('unset', '未设置', '尚未配置行情自动采集');
    case 'DISABLED':
      return statusView('unset', '未启用');
    case 'NOT_COLLECTED':
      return statusView('unset', '尚未采集');
    default:
      return statusView('error', '采集出错', failureReasonText(reason));
  }
}

function studySentence(study: Study, view: StatusView): string {
  if (view.kind === 'error' || view.kind === 'attention') {
    return view.reason ?? failureReasonText(study.reason ?? null);
  }
  if (study.portfolio !== undefined && study.portfolio !== null) {
    return '研究组合权重建议已保存，仅供研究参考。';
  }
  if (study.risk_rows !== undefined && study.risk_rows.length > 0) {
    return '已保存 ' + countText(study.risk_rows.length, '只') + '证券的波动预测，仅供研究参考。';
  }
  if (study.billing !== undefined) {
    return '研究产物已保存，' + (study.billing === 'LOCAL_NO_BILLING' ? '本地运行不产生费用。' : '费用以最终账单为准。');
  }
  return '研究产物已保存，详细来源见诊断信息。';
}

function evaluationSentence(evaluation: Evaluation, view: StatusView): string {
  if (view.kind === 'error' || view.kind === 'attention') {
    return view.reason ?? failureReasonText(evaluation.reason ?? null);
  }
  if (evaluation.verdict === 'STRUCTURALLY_UNREACHABLE') {
    return '当前协议样本量达不到预设门槛，证据不足以授予交易资格。';
  }
  return '已在本地核对报告完整性；证据不足以授予交易资格。';
}

function ReportHead({ name, meta, view }: { name: string; meta: string; view: StatusView }) {
  return (
    <div className="report-row__head">
      <div className="report-row__titles">
        <strong className="report-row__name">{name}</strong>
        <span className="report-row__meta">{meta}</span>
      </div>
      <StatusBadge status={view} size="sm" />
    </div>
  );
}

function StudyRow({ study }: { study: Study }) {
  const view = studyStatusView(study.state, study.reason ?? null);
  const time = study.received_at === undefined ? '时间未记录' : formatDateTime(study.received_at);
  return (
    <article className="study-row" data-testid="report-row">
      <ReportHead name={study.name} meta={studyKindText(study.kind) + ' · ' + time} view={view} />
      <p className="report-row__summary">{studySentence(study, view)}</p>
      <Diagnostics
        items={[
          { label: '研究记录 ID', value: study.id },
          { label: '关联任务 ID', value: study.task_id ?? '—' },
          { label: '数据模式', value: study.mode ?? '—' },
          { label: '结果摘要哈希', value: study.result_sha256 ?? '—' },
          { label: '费用状态', value: study.billing ?? '—' },
          { label: '状态原始值', value: study.state },
        ]}
        data={study}
      />
    </article>
  );
}

function EvaluationRow({ evaluation }: { evaluation: Evaluation }) {
  const view = studyStatusView(evaluation.state, evaluation.reason ?? null);
  return (
    <article className="study-row" data-testid="report-row">
      <ReportHead name={evaluation.name} meta={'本地评价报告 · 时间未记录'} view={view} />
      <p className="report-row__summary">{evaluationSentence(evaluation, view)}</p>
      <Diagnostics
        items={[
          { label: '评价记录 ID', value: evaluation.id },
          { label: '状态原始值', value: evaluation.state },
          { label: '结论原始值', value: evaluation.verdict ?? '—' },
          { label: '原因原始值', value: evaluation.reason ?? '—' },
        ]}
        data={evaluation}
      />
    </article>
  );
}

function MarketStatus({ market }: { market: NonNullable<Workspace['market']> }) {
  const view = marketStatusView(market.state, market.reason ?? null);
  const latestDay = market.latest === null ? null : formatDay(market.latest.source_day);
  const lastSuccess = market.last_successful_date === null ? null : formatDay(market.last_successful_date);
  const dataDate = latestDay === null || latestDay === '—' ? lastSuccess : latestDay;
  return (
    <section className="study-row report-market" data-testid="market-status">
      <div className="report-row__head">
        <div className="report-row__titles">
          <h3 className="report-market__title">行情采集状态</h3>
          <span className="report-row__meta">行情数据用于收盘后自动研究与研究报告</span>
        </div>
        <StatusBadge status={view} size="sm" />
      </div>
      <p className="report-row__summary">
        数据日期：{dataDate === null || dataDate === '—' ? '尚无已采集的数据日期' : dataDate}
      </p>
      {view.reason === undefined ? null : <p className="report-row__summary">{view.reason}</p>}
      <Diagnostics
        items={[
          { label: '采集状态原始值', value: market.state },
          { label: '数据模式', value: market.data_mode ?? '—' },
          { label: '最后成功日期（原始）', value: market.last_successful_date ?? '—' },
          { label: '缺口记录', value: countText(market.gaps.length, UNITS.item) },
        ]}
        data={market}
      />
    </section>
  );
}

function AdvancedRecords({ workspace }: { workspace: Workspace }) {
  const candidates = workspace.candidates;
  return (
    <details className="disclosure report-advanced">
      <summary className="disclosure__summary">
        <span>其他研究记录（{countText(candidates.length, UNITS.item)}）</span>
        <Icon name="chevron-down" />
      </summary>
      <div className="disclosure__body">
        {candidates.map((candidate, index) => (
          <article className="study-row" key={candidate.registry + ':' + String(index)}>
            <div className="report-row__titles">
              <strong className="report-row__name">研究记录</strong>
              <span className="report-row__meta">
                {candidate.registered_at === undefined ? '登记时间未记录' : formatDateTime(candidate.registered_at)}
              </span>
            </div>
            <p className="report-row__summary">登记或冻结只是研究记录，不代表已获交易资格。</p>
            <Diagnostics
              items={[
                { label: '登记库', value: candidate.registry },
                { label: '登记摘要哈希', value: candidate.registration_sha256 ?? '—' },
                { label: '候选摘要哈希', value: candidate.candidate_sha256 ?? '—' },
                { label: '关联任务 ID', value: candidate.task_id ?? '—' },
                { label: '数据模式', value: candidate.mode ?? '—' },
                { label: '状态原始值', value: candidate.state },
                { label: '原因原始值', value: candidate.reason ?? '—' },
              ]}
              data={candidate}
            />
          </article>
        ))}
      </div>
    </details>
  );
}

export function WorkspaceStudies({ workspace }: { workspace: WorkspaceState }) {
  const data = workspace.data;
  const hasReports = data !== null && (data.studies.length > 0 || data.evaluations.length > 0);
  const candidateCount = data === null ? 0 : data.candidates.length;
  return (
    <Card className="workspace-studies" data-testid="agent-reports">
      <CardHead
        title={TERMS.researchReport}
        actions={<Button variant="ghost" size="sm" icon="refresh" onClick={workspace.refresh}>刷新</Button>}
      />
      <CardBody>
        {workspace.error === null || (data === null && workspace.error.code === 'WORKSPACE_SCHEMA') ? null : (
          <Callout tone="danger" title="研究报告读取失败">
            {workspace.error.message}
            <Diagnostics items={[{ label: '原始错误码', value: workspace.error.code }]} />
          </Callout>
        )}
        {data === null ? (
          workspace.error === null ? (
            <p className="muted">正在读取研究报告…</p>
          ) : (
            <>
              <EmptyState
                compact
                icon="file"
                title={EMPTY.reportsTitle}
                description="本机还没有可读取的研究报告。完成研究后，结论会保存在这里。"
              />
              <Diagnostics items={[{ label: '原始错误码', value: workspace.error.code }]} />
            </>
          )
        ) : (
          <>
            {data.market === undefined ? null : <MarketStatus market={data.market} />}
            {hasReports ? (
              <div className="report-list">
                {data.studies.map((study) => <StudyRow key={study.id} study={study} />)}
                {data.evaluations.map((evaluation) => <EvaluationRow key={'evaluation:' + evaluation.id} evaluation={evaluation} />)}
              </div>
            ) : (
              <EmptyState
                compact
                icon="file"
                title={EMPTY.reportsTitle}
                description={data.state === 'ready' ? '完成研究后，结论会保存在这里。' : '本机还没有连接研究资料目录。完成研究后，结论会保存在这里。'}
              />
            )}
            {candidateCount === 0 ? null : <AdvancedRecords workspace={data} />}
          </>
        )}
      </CardBody>
    </Card>
  );
}
