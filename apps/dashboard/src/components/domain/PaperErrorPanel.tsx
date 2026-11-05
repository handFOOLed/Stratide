import type { ApiError } from '../../lib/api';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Card } from '../ui/Card';
import { Diagnostics } from '../ui/Diagnostics';
import { humanReasonText } from '../../lib/status';

function describe(error: Pick<ApiError, 'code' | 'message'>): { title: string; detail: string } {
  switch (error.code) {
    case 'CURRENT_PAPER_ACCOUNT_UNCONFIGURED':
      return {
        title: '尚未配置模拟账户',
        detail: '完成安装向导后会显示模拟账户资产；历史记录仍可在交易记录中查看。',
      };
    case 'NO_SNAPSHOT':
      return {
        title: '尚未设置模拟账户',
        detail: '在安装向导或本机设置中指定一个已发布的模拟账户数据目录后，这里会显示资产与交易记录。',
      };
    case 'INVALID_SNAPSHOT':
      return {
        title: '模拟账户数据不可用',
        detail: humanReasonText(error.message) ?? '数据缺失、损坏或格式不支持。修复后重新读取。',
      };
    case 'OFFLINE':
    case 'TIMEOUT':
      return {
        title: '无法连接本地服务',
        detail: '请确认 Stratide 后台服务正在运行，然后重新读取。',
      };
    case 'SNAPSHOT_CHANGED':
      return {
        title: '数据在读取期间发生变化',
        detail: '为避免把两份数据混在一起，已停止显示。请重新读取。',
      };
    default:
      return {
        title: '账户数据读取失败',
        detail: humanReasonText(error.message) ?? '本地服务返回了未预期的错误。',
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
        actions={
          <Button variant="secondary" icon="refresh" onClick={onRetry}>
            重新读取
          </Button>
        }
      />
      <div className="paper-error-card__diagnostics">
        <Diagnostics
          title="读取诊断信息"
          items={[
            { label: '状态', value: error.code },
            { label: '提示', value: error.message },
            { label: '读取方式', value: '本机只读接口' },
          ]}
          data={error}
        />
      </div>
    </Card>
  );
}
