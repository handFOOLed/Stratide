import { useCallback, useEffect, useState } from 'react';
import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Diagnostics } from '../components/ui/Diagnostics';
import { useToast } from '../components/ui/Toast';
import { readInbox, readNotices } from '../lib/workspace';
import type { Inbox, Notice } from '../lib/workspace';
import { friendlyError } from '../lib/api';
import { countText, formatDateTime } from '../lib/format';
import { notificationTitle, taskStatusView } from '../lib/status';
import { navigate } from '../lib/route';
import type { AgentState } from '../state/useAgent';
import { useInterval } from '../lib/hooks';
import { EMPTY } from '../lib/copy';

/** 通知标题：后端 kind 明确区分“研究未运行”和普通研究任务。 */
function noticeTitle(notice: Notice): string {
  return notice.kind === 'research_blocked_notice' ? '研究未运行' : notificationTitle(notice.status);
}

/** 一句话结果：状态原因优先，完成态使用后端截断后的结论。 */
function noticeSentence(notice: Notice): string {
  const status = taskStatusView(notice.status, notice.reason, notice.conclusion);
  if (status.reason !== undefined && status.reason !== '') return status.reason;
  return notice.conclusion ?? '可在任务详情查看结果';
}

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

  const markRead = async (ids: string[]) => {
    if (token === null || ids.length === 0) return;
    setBusy(ids.length === 1 ? ids[0] : 'all');
    try {
      await readNotices(token, ids);
      await refresh();
      toast.push({ title: ids.length === 1 ? '已标为已读' : '本页已标为已读', tone: 'success' });
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
  const pageUnread = notifications.filter((notice) => !notice.read);
  const totalUnread = inbox === null ? 0 : inbox.unread_count;
  const allUnreadMarked = pageUnread.length > 0 && pageUnread.length === totalUnread;

  return (
    <>
      <PageHeader title="通知" titleRef={titleRef} />
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <Card>
        <CardHead
          title="研究通知"
          subtitle={
            notifications.length === 0
              ? '研究任务结束后，结果会出现在这里'
              : totalUnread > 0
                ? countText(totalUnread, '条') + '未读'
                : '全部已读'
          }
          actions={
            <Button
              variant="ghost"
              size="sm"
              disabled={pageUnread.length === 0 || busy !== null}
              loading={busy === 'all'}
              onClick={() => void markRead(pageUnread.map((notice) => notice.id))}
            >
              {allUnreadMarked ? '全部标为已读' : '标记本页已读'}
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
              const status = taskStatusView(notice.status, notice.reason, notice.conclusion);
              const subject = notice.name === null ? '' : notice.name.trim();
              return (
                <li key={notice.id} className="notice-row" data-read={notice.read ? 'true' : 'false'}>
                  <span className="notice-dot" aria-hidden="true" />
                  {notice.read ? null : <span className="sr-only">未读</span>}
                  <div className="notice-body">
                    <div className="notice-title-row">
                      <span className="notice-title">{noticeTitle(notice)}</span>
                      <StatusBadge status={status} size="sm" />
                    </div>
                    <p className="notice-result">{noticeSentence(notice)}</p>
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
              { label: '本页通知条数', value: String(notifications.length) },
              { label: '本页未读条数', value: String(pageUnread.length) },
              { label: '全部未读条数', value: String(totalUnread) },
            ]}
            data={{ notifications, approvals: inbox?.approvals ?? [], unread_count: inbox?.unread_count ?? null }}
          />
        </div>
      </Card>
    </>
  );
}
