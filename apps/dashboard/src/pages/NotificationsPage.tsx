import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardFoot, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Icon } from '../icons';
import type { HealthState } from '../state/useHealth';

export function NotificationsPage({ health, titleRef }: { health: HealthState; titleRef?: Ref<HTMLHeadingElement> }) {
  const notificationsStatus = health.data?.notifications ?? null;
  const statusText = health.checking && !health.checkedAt
    ? '读取中'
    : health.error
      ? '状态不可读'
      : notificationsStatus ?? 'unknown';
  return (
    <>
      <PageHeader
        title="通知审批"
        titleRef={titleRef}
      />

      <div className="grid notifications-grid">
        <div className="col-6">
          <Card className="notification-card">
            <CardHead
              title="通知渠道"
              actions={<Badge tone="neutral">未接入</Badge>}
            />
            <CardBody>
              <div className="notification-empty">
                <span className="notification-empty__icon"><Icon name="notifications" /></span>
                <h3>暂无可用渠道</h3>
              </div>
            </CardBody>
            <CardFoot>
              <span>服务状态</span>
              <code className="code-chip">{statusText}</code>
            </CardFoot>
          </Card>
        </div>
        <div className="col-6">
          <Card className="notification-card">
            <CardHead
              title="审批"
              actions={<Badge tone="neutral">未接入</Badge>}
            />
            <CardBody>
              <div className="notification-empty">
                <span className="notification-empty__icon"><Icon name="shield" /></span>
                <h3>审批服务未接入</h3>
              </div>
            </CardBody>
            <CardFoot>
              <span>通过本机可信流程授权</span>
            </CardFoot>
          </Card>
        </div>
      </div>

    </>
  );
}
