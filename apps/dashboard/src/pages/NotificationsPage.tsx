import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardFoot, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Callout } from '../components/ui/Callout';
import { Icon } from '../icons';
import type { HealthState } from '../state/useHealth';

export function NotificationsPage({ health, titleRef }: { health: HealthState; titleRef?: Ref<HTMLHeadingElement> }) {
  const notificationsStatus = health.data?.notifications ?? null;
  const statusText = health.checking && !health.checkedAt
    ? '正在读取本机健康状态'
    : health.error
      ? '当前无法读取本机健康状态'
      : '服务端 /api/health 当前报告 notifications=' + (notificationsStatus ?? 'unknown');
  return (
    <>
      <PageHeader
        eyebrow="Inbox"
        title="通知与审批"
        description="只展示真实存在的待办、告警与审批。当前通知渠道与审批服务尚未接入，本页不会用占位数据填充。"
        titleRef={titleRef}
        side={<Badge tone="outline">服务未接入</Badge>}
      />

      <Callout tone="info" title="这里没有伪造的通知">
        {statusText}。没有已配置的通知渠道，也没有发送过任何消息；审批服务没有读取或写入 API。
      </Callout>

      <div className="grid notifications-grid">
        <div className="col-6">
          <Card className="notification-card">
            <CardHead
              title="通知渠道"
              subtitle="事件推送、每日摘要与异常提醒"
              actions={<Badge tone="neutral">未接入</Badge>}
            />
            <CardBody>
              <div className="notification-empty">
                <span className="notification-empty__icon"><Icon name="notifications" /></span>
                <h3>没有可用渠道</h3>
                <p>当前没有已配置的邮件、桌面或远程通知通道。页面不会声称发送过消息，也不会用旧事件伪造未读列表。</p>
              </div>
            </CardBody>
            <CardFoot>
              <span>API 原值</span>
              <code className="code-chip">{notificationsStatus ?? (health.checking ? '读取中' : '无法读取')}</code>
            </CardFoot>
          </Card>
        </div>
        <div className="col-6">
          <Card className="notification-card">
            <CardHead
              title="审批"
              subtitle="资金、权限与不可逆操作的明确授权"
              actions={<Badge tone="neutral">未接入</Badge>}
            />
            <CardBody>
              <div className="notification-empty">
                <span className="notification-empty__icon"><Icon name="shield" /></span>
                <h3>没有审批 API</h3>
                <p>本机只读服务不提供审批读取或写入。Web 不提供资本加额、风险锁清除、模型密钥写入或实盘授权按钮。</p>
              </div>
            </CardBody>
            <CardFoot>
              <span>Owner 授权仍走本机可信流程</span>
            </CardFoot>
          </Card>
        </div>
      </div>

      <Card className="notifications-principles">
        <CardHead title="本页的边界" subtitle="接入后也只显示需要处理的事件，不复制其他页面的仪表盘" />
        <CardBody>
          <ul className="principle-list">
            <li>
              <span className="principle-list__index">01</span>
              <div><strong>只显示真实事件</strong><p>风险锁、估值缺失、预算耗尽或需要 Owner 决定的事项；没有事件时保持空态。</p></div>
            </li>
            <li>
              <span className="principle-list__index">02</span>
              <div><strong>不把通知当操作权限</strong><p>通知可以提示，但不能绕过 Risk Kernel、预算 Gate、Owner veto 或独立验收。</p></div>
            </li>
            <li>
              <span className="principle-list__index">03</span>
              <div><strong>不使用其他页面的数据看板</strong><p>这里不重复 NAV、持仓、Agent 预算或研究任务表格；需要上下文时只给出必要摘要。</p></div>
            </li>
          </ul>
        </CardBody>
      </Card>
    </>
  );
}