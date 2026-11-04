/* §2.1/§2.8: choose a registered experiment, then review the exact permission. */
import { useEffect, useState } from 'react';
import { Card, CardBody, CardHead } from '../ui/Card';
import { Button } from '../ui/Button';
import { agentFetch, friendlyError } from '../../lib/api';
import { readOperations, requestOperation } from '../../lib/workspace';
import type { Operation } from '../../lib/workspace';
import { TechnicalDetails } from './WorkspaceStudies';
import { navigate } from '../../lib/route';

export function ResearchOperations({token}: {token: string}) {
  const [operations,setOperations]=useState<Operation[]>([]);
  const [prompt,setPrompt]=useState<unknown>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{
    const controller=new AbortController();
    void Promise.all([readOperations(token),agentFetch<unknown>(token,'prompts',{signal:controller.signal})])
      .then(([v,p])=>{if (!controller.signal.aborted){setOperations(v.operations);setPrompt(p);}})
      .catch(e=>{if (!controller.signal.aborted)setMessage(friendlyError(e).message);});
    return ()=>controller.abort();
  },[token]);
  const request=async(op:Operation)=>{
    setBusy(true);
    try {await requestOperation(token,crypto.randomUUID().replaceAll('-',''),op.id);navigate({page:'notifications'});}
    catch(e){setMessage(friendlyError(e).message);}
    finally{setBusy(false);}
  };
  return <Card><CardHead title="发起冻结研究" actions={<Button variant="ghost" disabled={busy} onClick={async()=>{setBusy(true);try{await agentFetch(token,'stop-local',{method:'POST',body:{}});setMessage('本地研究已请求停止；原任务保留。');}catch(e){setMessage(friendlyError(e).message);}finally{setBusy(false);}}}>停止本地研究</Button>}/><CardBody>
    <p className="muted">仅执行本机已配置的实验；审批不增加预算、外发范围或交易权限。</p>
    {operations.length===0?<p className="compact-empty">尚未配置可运行实验。选择本机原冻结批次后即可从这里发起。</p>:operations.map(op=><div className="study-row study-row__title" key={op.id}><div><strong>{op.label}</strong><p>{op.kind==='local_timesfm'?'TimesFM CPU · 本地不计费':op.kind==='risk_evaluation'?'独立评价入口 · 本地不计费':op.kind==='recorded_fusion'?'离线录制 Fusion · TST，非真实账单':'合成来源 · 原云授权与预算 Gate'}</p><span className="muted">批次 {op.batch}</span></div><Button disabled={busy} onClick={()=>void request(op)}>提交审批</Button></div>)}
    {message?<p role="alert">{message}</p>:null}
    <details className="technical-details"><summary>版本化内置 Prompt（只读安全版）</summary><TechnicalDetails value={prompt}/></details>
  </CardBody></Card>;
}
