import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Diagnostics } from '../components/ui/Diagnostics';
import { useToast } from '../components/ui/Toast';
import { readInbox, readNotices } from '../lib/workspace';
import type { Inbox } from '../lib/workspace';
import { friendlyError } from '../lib/api';
import { formatDateTime } from '../lib/format';
import { countText } from '../lib/format';
import { notificationTitle, researchTaskName, taskStatusView } from '../lib/status';
import { navigate } from '../lib/route';
import type { AgentState } from '../state/useAgent';
import { useInterval } from '../lib/hooks';
import { EMPTY } from '../lib/copy';

export function NotificationsPage({ agent, titleRef }: { agent: AgentState; titleRef?: Ref<HTMLHeadingElement> }) {
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const token = agent.token;

  const refresh = useCallback(async () => {
    if (token === null) return;
    try {
      setInbox(await readInbox(token));
      setError('');
    } catch (caught) {
      setError(friendlyError(caught).message);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);
  useInterval(() => void refresh(), token === null ? null : 8000);

  const taskById = useMemo(() => {
    const map = new Map<string, (typeof agent.tasks)[number]>();
    for (const task of agent.tasks) map.set(task.id, task);
    return map;
  }, [agent.tasks]);

  const markRead = async (ids: string[]) => {
    if (token === null || ids.length === 0) return;
    setBusy(ids.length === 1 ? ids[0] : 'all');
    try {
      await readNotices(token, ids);
      await refresh();
      toast.push({ title: ids.length === 1 ? '已标为已读' : '全部标为已读', tone: 'success' });
    } catch (caught) {
      toast.push({ title: '操作未完成', description: friendlyError(caught).message, tone: 'danger' });
    } finally {
      setBusy(null);
    }
  };

  const openTask = (id: string) => {
    void agent.openTask(id);
    navigate({ page: 'agents' });
  };

  const notifications = inbox?.notifications ?? [];
  const unread = notifications.filter((notice) => !notice.read);

  return (
    <>
      <PageHeader title="通知" titleRef={titleRef} />
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <Card>
        <CardHead
          title="研究通知"
          subtitle={notifications.length === 0 ? '研究任务结束后，结果会出现在这里' : countText(unread.length, '条') + '未读'}
          actions={
            <Button
              variant="ghost"
              size="sm"
              disabled={unread.length === 0 || busy !== null}
              loading={busy === 'all'}
              onClick={() => void markRead(unread.map((notice) => notice.id))}
            >
              全部标为已读
            </Button>
          }
        />
        {inbox === null ? (
          <p className="muted notice-loading">正在读取通知…</p>
        ) : notifications.length === 0 ? (
          <EmptyState compact icon="notifications" title={EMPTY.noticesTitle} description={EMPTY.noticesBody} />
        ) : (
          <ul className="notice-list" aria-label="研究通知">
            {notifications.map((notice) => {
              const task = taskById.get(notice.id);
              const status = taskStatusView(notice.status, notice.reason, task?.conclusion ?? null);
              const title = task !== undefined && task.provider_id === 'market-research-status'
                ? '研究未运行'
                : notificationTitle(notice.status);
              const subject = task === undefined ? '' : researchTaskName(task.created_at, task.name);
              const result = status.reason ?? (status.kind === 'ok' ? '研究已完成，可在任务详情查看结论' : '可在任务详情查看结果');
              return (
                <li key={notice.id} className="notice-row" data-read={notice.read ? 'true' : 'false'}>
                  <span className="notice-dot" aria-hidden="true" />
                  {notice.read ? null : <span className="sr-only">未读</span>}
                  <div className="notice-body">
                    <div className="notice-title-row">
                      <span className="notice-title">{title}</span>
                      <StatusBadge status={status} size="sm" />
                    </div>
                    <p className="notice-result">{result}</p>
                    <div className="notice-meta">
                      {subject === '' ? null : <span>{subject}</span>}
                      <span>{formatDateTime(notice.at)}</span>
                    </div>
                  </div>
                  <div className="notice-actions">
                    <Button size="sm" variant="secondary" onClick={() => openTask(notice.id)}>
                      查看任务
                    </Button>
                    {notice.read ? null : (
                      <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void markRead([notice.id])}>
                        标为已读
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <div className="card__foot">
          <Diagnostics
            title="通知记录诊断信息"
            items={[
              { label: '通知条数', value: String(notifications.length) },
              { label: '未读条数', value: String(unread.length) },
            ]}
            data={{ notifications, approvals: inbox?.approvals ?? [] }}
          />
        </div>
      </Card>
    </>
  );
}
