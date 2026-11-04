import { useCallback, useEffect, useState } from 'react';
import { ApiError, agentFetch, friendlyError } from './api';

export interface Operation { id: string; label: string; kind: string; batch: string }
export interface Approval {
  id: string; action: Operation; status: string; created_at: string; expires_at: number;
  decided_at: string | null; started_at: string | null; finished_at: string | null; reason: string | null;
  action_sha256: string;
}
export interface Notice {id: string; status: string; reason: string | null; at: string; read: boolean}
export interface Inbox {approvals: Approval[]; notifications: Notice[]; authority: string}
export interface Study {
  id: string; name: string; kind: string; state: string; mode?: string; task_id?: string;
  billing?: string; reason?: string | null; result_sha256?: string | null; summary?: unknown;
  received_at?:string;
  risk_rows?: Array<{instrument:string;as_of:string;forecasts:Array<{sessions:number;value_ratio:number}>;naive:number;ewma:number;quality:string[]}>;
  portfolio?: {positions:Array<{instrument:string;weight_bps:number}>;cash_weight_bps:number} | null;
}
export interface Evaluation {id: string; name: string; state: string; reason?: string; summary?: unknown; report?: unknown;verdict?:string;
  split_rows?:Array<{name:string;samples:number;scored:number;status:string;coverage:number;metrics:Array<{model:string;horizon:string;mae:number;rmse:number}>}>}
export interface Evidence {id: string; name: string; state: string; sha256?: string; report?: unknown; reason?: string}
export interface Workspace {
  schema_version: 1; state: string; studies: Study[]; evaluations: Evaluation[]; evidence: Evidence[];
  candidates:Array<{registry:string;state:string;registration_sha256?:string;candidate_sha256?:string;mode?:string;task_id?:string;registered_at?:string;reason?:string}>;
  paper_allowed: false; live_allowed: false;
  admission?:{matrix:Array<{dependency:string;status:string;reason:string;required_evidence:string;issue:string}>};
  backup?:{state:string;files?:number;manifest_sha256?:string};
  market?: {state:string;reason?:string;data_mode?:string;last_successful_date:string|null;gaps:unknown[];
    latest:null|{source_day:string;state:string;expected_market:number;actual_quoted:number;market_explained:number;
      market_coverage_bps:number;research_denominator:number;eligible_count:number;categories:Record<string,number>;
      available_at:string;source_states:Record<string,string>;blockers:string[];snapshot_sha256:string}};
}
export interface WorkspaceState {data: Workspace | null; error: ApiError | null; refresh: () => void}

export function useWorkspace(): WorkspaceState {
  const [data, setData] = useState<Workspace | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion(v => v + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const r = await fetch('/api/v1/workspace', {signal: controller.signal, cache: 'no-store'});
        const v = await r.json();
        if (!r.ok) throw new ApiError(v.error.code, '本地研究资料读取失败；请在技术详情核对原因。', r.status);
        const w: Workspace = v.data;
        if (w.schema_version !== 1 || !Array.isArray(w.studies) || !Array.isArray(w.evaluations) || !Array.isArray(w.evidence) || !Array.isArray(w.candidates) || w.paper_allowed !== false || w.live_allowed !== false) throw new ApiError('WORKSPACE_SCHEMA', '研究响应版本不兼容。');
        setData(w); setError(null);
      } catch (e) {if (!controller.signal.aborted) setError(friendlyError(e));}
    })();
    return () => controller.abort();
  }, [version]);
  return {data, error, refresh};
}

export const readInbox = (token: string) => agentFetch<Inbox>(token, 'inbox');
export const readOperations = (token: string) => agentFetch<{operations: Operation[]}>(token, 'operations');
export const requestOperation = (token: string, id: string, operation: string) => agentFetch<Approval>(token, 'approvals', {method:'POST', body:{id,operation}});
export const decideApproval = (token: string, id: string, decision: string) => agentFetch<Approval>(token, 'decide', {method:'POST', body:{id,decision}});
export const readNotices = (token: string, ids: string[]) => agentFetch<unknown>(token, 'read-notifications', {method:'POST',body:{ids}});

const states: Record<string,string> = {
  RESEARCH_ONLY:'仅供研究',REGISTERED:'已登记',FROZEN_CANDIDATE:'候选已冻结',
  NOT_BILLED:'离线录制，不是真实云调用或账单',
  reserved:'已预留',dispatched:'已派发',usage_received:'用量估算已记录',settled:'已核验账单',no_charge:'确认未计费',
  pending:'待审批', approved:'已许可，尚未执行', rejected:'已拒绝', revoked:'已撤销', expired:'已过期',
  running:'运行中', local_running:'本地研究中', completed:'已完成', failed:'失败', cancelled:'已取消', cancel_requested:'取消待确认',
  outcome_uncertain:'调用结果未知', BLOCKED:'受阻', ready:'可读取', not_configured:'未配置',
  historical_research_only:'事后历史研究', synthetic_test:'合成测试', forward_observed_eod:'前向盘后观察',
  FROZEN_NOT_RUN:'输入已冻结，尚未运行', LOCAL_NO_BILLING:'本地运行，不计费',
  ESTIMATED_NOT_VERIFIED_BILL:'估算费用，非核验账单', verified_local_integrity:'本地完整性已核对',
  stored_evidence_not_qualification:'已有来源记录，非交易资格',
};
export function stateLabel(state: string): string {return Object.hasOwn(states,state) ? states[state] : '待核对（见技术详情）';}
