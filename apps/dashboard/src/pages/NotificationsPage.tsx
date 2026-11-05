import { useCallback, useEffect, useRef, useState } from 'react';
import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { readInbox, readNotices, stateLabel } from '../lib/workspace';
import type { Inbox } from '../lib/workspace';
import { friendlyError } from '../lib/api';
import { formatDateTime } from '../lib/format';
import type { AgentState } from '../state/useAgent';
import { useInterval } from '../lib/hooks';

export function NotificationsPage({ agent, titleRef }: { agent: AgentState; titleRef?: Ref<HTMLHeadingElement> }) {
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState('');
  const [pendingRead, setPendingRead] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
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
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [refresh]);
  useInterval(() => void refresh(), token === null ? null : 6000);

  const markRead = () => {
    if (token === null || inbox === null || inbox.notifications.length === 0) return;
    const first = inbox.notifications[0];
    if (first === undefined) return;
    setPendingRead(first.id);
    timer.current = window.setTimeout(() => {
      void readNotices(token, inbox.notifications.map((notice) => notice.id))
        .then(() => {
          setPendingRead(null);
          void refresh();
        })
        .catch((caught) => {
          setPendingRead(null);
          setError(friendlyError(caught).message);
        });
      timer.current = null;
    }, 5000);
  };

  return (
    <>
      <PageHeader title="通知" titleRef={titleRef} />
      {error ? <p role="alert">{error}</p> : null}
      <Card>
        <CardHead
          title="任务通知"
          actions={
            <Button variant="ghost" size="sm" disabled={pendingRead !== null || inbox === null || inbox.notifications.length === 0} onClick={markRead}>
              标为已读
            </Button>
          }
        />
        <CardBody>
          {pendingRead !== null ? (
            <div role="status" className="inline-row">
              <span>5 秒后标为已读</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  if (timer.current !== null) window.clearTimeout(timer.current);
                  timer.current = null;
                  setPendingRead(null);
                }}
              >
                撤销
              </Button>
            </div>
          ) : null}
          {inbox === null ? (
            <p className="muted">正在读取记录…</p>
          ) : inbox.notifications.length === 0 ? (
            <EmptyState compact icon="notifications" title="还没有通知" description="研究任务结束或出错时会出现在这里。" />
          ) : (
            inbox.notifications.map((notice) => (
              <article className="study-row" key={notice.id}>
                <div className="study-row__title">
                  <strong>任务 #{notice.id} · {stateLabel(notice.status)}</strong>
                  <span>{notice.read ? '已读' : '未读'}</span>
                </div>
                <p>{formatDateTime(notice.at)}</p>
              </article>
            ))
          )}
        </CardBody>
      </Card>
    </>
  );
}
