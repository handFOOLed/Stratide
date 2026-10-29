import type { ApiError } from '../../lib/api';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Card } from '../ui/Card';

function describe(error: Pick<ApiError, 'code' | 'message'>): { title: string; detail: string; hint?: string } {
  switch (error.code) {
    case 'NO_SNAPSHOT':
      return {
        title: '尚未选择 Paper 报告',
        detail:
          '启动时通过 --report-dir 指定一个已发布的完整六报告目录。服务不会自动寻找“最近实验”，没有默认资金或默认测试账户。',
        hint: 'pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir <目录>',
      };
    case 'INVALID_SNAPSHOT':
      return {
        title: 'Paper 报告不可用',
        detail:
          error.message ||
          '六报告缺失、损坏、格式不支持或在读取期间发生变化。修复报告后，以同一明确目录重启服务。',
      };
    case 'OFFLINE':
    case 'TIMEOUT':
      return {
        title: '无法连接本地服务',
        detail:
          '请确认 Windows 本机的 stratided 服务仍在运行。该服务只绑定 127.0.0.1，不提供远程访问。',
        hint: 'pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir <目录>',
      };
    case 'SNAPSHOT_CHANGED':
      return {
        title: '读取期间快照发生变化',
        detail:
          '不同接口返回了不同的 snapshot_id，已停止组合显示，避免把两份报告混在一起。请重新读取。',
      };
    default:
      return {
        title: '账户数据读取失败',
        detail: error.message || '本地服务返回了未预期的错误。',
      };
  }
}

export function PaperErrorPanel({
  error,
  onRetry,
}: {
  error: Pick<ApiError, 'code' | 'message' | 'status'>;
  onRetry: () => void;
}) {
  const info = describe(error);
  return (
    <Card className="paper-error-card">
      <EmptyState
        tone="error"
        icon="alert-triangle"
        title={info.title}
        description={info.detail}
        code={error.code + (error.status ? ' · HTTP ' + String(error.status) : '')}
        actions={
          <Button variant="secondary" icon="refresh" onClick={onRetry}>
            重新读取
          </Button>
        }
      />
      {info.hint ? (
        <div className="command-hint">
          <span className="command-hint__label">启动示例</span>
          <code>{info.hint}</code>
        </div>
      ) : null}
    </Card>
  );
}