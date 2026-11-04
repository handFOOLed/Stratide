/* §2.1/§3.6: 60% decisions, 40% durable task notices. */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { TechnicalDetails } from '../components/domain/WorkspaceStudies';
import { decideApproval, readInbox, readNotices, stateLabel } from '../lib/workspace';
import type { Inbox } from '../lib/workspace';
import { friendlyError } from '../lib/api';
import { formatDateTime } from '../lib/format';
import { navigate } from '../lib/route';
import type { AgentState } from '../state/useAgent';
import { useInterval } from '../lib/hooks';

export function NotificationsPage({agent,titleRef}: {agent: AgentState; titleRef?: Ref<HTMLHeadingElement>}) {
  const [inbox,setInbox]=useState<Inbox | null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [pendingRead,setPendingRead]=useState<string | null>(null);
  const timer=useRef<number | null>(null);
  const token=agent.token;
  const refresh=useCallback(async()=>{
    if (token===null) return;
    try {setInbox(await readInbox(token));setError('');}
    catch(e){setError(friendlyError(e).message);}
  },[token]);
  useEffect(()=>{void refresh();return ()=>{if(timer.current!==null)window.clearTimeout(timer.current);};},[refresh]);
  useInterval(()=>void refresh(),token===null?null:6000);
  const decide=async(id:string,decision:string)=>{
    if(token===null)return;
    setBusy(true);
    try {await decideApproval(token,id,decision);await refresh();}
    catch(e){setError(friendlyError(e).message);}
    finally{setBusy(false);}
  };
  const markRead=()=>{
    if(token===null||inbox===null||inbox.notifications.length===0)return;
    const first=inbox.notifications[0];
    if(first===undefined)return;
    setPendingRead(first.id);
    // Only a reversible local presentation action gets a five-second undo.
    timer.current=window.setTimeout(()=>{
      void readNotices(token,inbox.notifications.map(n=>n.id)).then(()=>{setPendingRead(null);void refresh();}).catch(e=>{setPendingRead(null);setError(friendlyError(e).message);});
      timer.current=null;
    },5000);
  };
  return <><PageHeader title="通知审批" titleRef={titleRef}/>
    {token===null?<Card><CardBody><p>本机研究控制尚未解锁。</p><Button onClick={()=>navigate({page:'agents'})}>前往 Agent 管理解锁</Button></CardBody></Card>:<>
      {error?<p role="alert">{error}</p>:null}
      <div className="approval-layout"><Card><CardHead title="研究审批"/><CardBody>
        <p className="muted">核对冻结批次后显式许可，再执行；原预算与数据授权继续生效。</p>
        {inbox===null?<p>正在读取记录。</p>:inbox.approvals.length===0?<p className="compact-empty">暂无审批。从 Agent 管理提交本机已配置的研究。</p>:inbox.approvals.map(a=><article className="study-row" key={a.id}>
          <div className="study-row__title"><strong>{a.action.label}</strong><span>{stateLabel(a.status)}</span></div>
          <p>批次 {a.action.batch} · 创建 {formatDateTime(a.created_at)}</p>
          <p className="muted">有效至 {formatDateTime(new Date(a.expires_at*1000).toISOString())}{a.decided_at?' · Owner 决定 '+formatDateTime(a.decided_at):''}</p>
          <div className="inline-row">
            {a.status==='pending'?<><Button disabled={busy} onClick={()=>void decide(a.id,'approve')}>许可本次研究</Button><Button variant="ghost" disabled={busy} onClick={()=>void decide(a.id,'reject')}>拒绝</Button></>:null}
            {a.status==='approved'?<Button disabled={busy} onClick={()=>void decide(a.id,'start')}>执行已许可研究</Button>:null}
            {a.status==='approved'||a.status==='pending'?<Button variant="ghost" disabled={busy} onClick={()=>void decide(a.id,'revoke')}>撤销许可</Button>:null}
            {a.status==='running'?<span>已交原 Worker；进程中断后需核对原任务，不自动重发。</span>:null}
          </div><TechnicalDetails value={a}/>
        </article>)}
      </CardBody></Card><Card><CardHead title="任务通知" actions={<Button variant="ghost" size="sm" disabled={pendingRead!==null} onClick={markRead}>标为已读</Button>}/><CardBody>
        {pendingRead!==null?<div role="status" className="inline-row"><span>5 秒后标为已读</span><Button size="sm" variant="ghost" onClick={()=>{if(timer.current!==null)window.clearTimeout(timer.current);timer.current=null;setPendingRead(null);}}>撤销</Button></div>:null}
        {inbox===null?<p>正在读取记录。</p>:inbox.notifications.length===0?<p className="compact-empty">暂无已结束任务通知。</p>:inbox.notifications.map(n=><article className="study-row" key={n.id}><div className="study-row__title"><strong>任务 #{n.id} · {stateLabel(n.status)}</strong><span>{n.read?'已读':'未读'}</span></div><p>{formatDateTime(n.at)}</p><TechnicalDetails value={n}/></article>)}
      </CardBody></Card></div>
    </>}
  </>;
}
