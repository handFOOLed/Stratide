import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { Field, TextInput } from '../ui/Field';
import { SegmentedControl } from '../ui/SegmentedControl';
import { StatusBadge } from '../ui/StatusBadge';
import { BudgetEditor } from './BudgetEditor';
import { ApiError, agentFetch, friendlyError } from '../../lib/api';
import { formatDateTime, formatMicroMoney } from '../../lib/format';
import { statusView } from '../../lib/status';
import type { AgentState } from '../../state/useAgent';

interface Budget {
  currency: string;
  timezone: string;
  daily_limit_micro: number;
  monthly_limit_micro: number;
}

interface ProviderStatus {
  provider: string | null;
  configured_at: string | null;
  key_present: boolean;
  key_hint: string | null;
  model_installed: boolean;
  research_provider: 'deepseek' | null;
  research_key_present: boolean;
  research_price: {
    state: 'VALID' | 'REVIEW_REQUIRED' | 'EXPIRED';
    valid_until: string | null;
    reviewable: boolean;
    version: string;
    source: string;
    input_micro_per_million: string;
    output_micro_per_million: string;
  } | null;
  budget: Budget | null;
  endpoint: string | null;
}

const PROVIDER_LABELS: Record<string, string> = { deepseek: 'DeepSeek 官方', openai: 'OpenAI 官方' };

/** 研究服务配置错误 → 一句话原因；原始码只进“诊断信息”。 */
const SERVICE_REASON_TEXT: Record<string, string> = {
  MARKET_MODEL_ALREADY_INSTALLED: '研究模型配置已经写入过，无需重复配置。',
  MARKET_PROVIDER_CONFIGURATION_REQUIRED: '请先保存 DeepSeek API Key。',
  BUDGET_UNCONFIGURED: '尚未设置研究预算，暂时无法配置研究模型。',
  MARKET_SHARED_BUDGET_CAP_REQUIRED: '研究预算不符合共享上限要求。',
  PRICE_UNBOUNDED: '研究模型的价格配置超出允许范围。',
  AUTHORIZATION_REQUIRED: '研究模型的授权配置不完整。',
  MARKET_CONFIG_WRITE: '本机研究配置写入失败，请检查本机目录写入权限。',
  PROVIDER_SELECTION_CHANGED: '已保存的连接配置已变更，请重新读取后再测试。',
  DEEPSEEK_PRICE_REVIEW_REQUIRED: '请核对当前 DeepSeek 价格上限并明确确认。',
  DEEPSEEK_PRICE_EXPIRED_REFRESH_FROZEN_CONFIG: 'DeepSeek 价格审核已过期，请在本页重新确认。',
  RISK_BINDING_REQUIRED: '本机研究实例尚未完成绑定，无法保存研究模型。',
};

function errorReason(error: ApiError): string {
  return SERVICE_REASON_TEXT[error.code] ?? error.message;
}

export function ProviderPanel({ agent }: { agent: AgentState }) {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [selection, setSelection] = useState<string | null>(null);
  const [key, setKey] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [priceConfirmed, setPriceConfirmed] = useState(false);
  const agentToken = agent.token ?? 'local';
  const savedProvider = status?.provider ?? null;
  const provider = selection ?? savedProvider ?? 'deepseek';
  const price = status?.research_price ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await agentFetch<ProviderStatus>(agentToken, 'provider');
      setStatus(next);
      setError(null);
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setLoading(false);
    }
  }, [agentToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setError(null);
    setNotice(null);
    setBusy('save');
    try {
      const next = await agentFetch<ProviderStatus>(agentToken, 'provider', {
        method: 'POST',
        body: { provider, key },
      });
      setStatus(next);
      setKey('');
      setEditing(false);
      setSelection(null);
      setPriceConfirmed(false);
      setNotice(provider === 'openai'
        ? 'OpenAI 连接配置已保存。全市场研究使用独立的 DeepSeek 配置。'
        : 'DeepSeek 密钥已保存在本机。价格审核状态见下方。');
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setError(null);
    setNotice(null);
    setBusy('test');
    try {
      const result = await agentFetch<{ state: string; provider: string }>(agentToken, 'provider/test', {
        method: 'POST',
        body: { provider },
      });
      if (result.state === 'OK' && result.provider === provider) {
        setNotice(PROVIDER_LABELS[provider] + '模型列表接口连接成功。此测试只读取模型列表。');
      } else {
        setError(new ApiError('PROVIDER_TEST_UNCONFIRMED', '连接结果未确认，请检查 API Key 与网络。'));
      }
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(null);
    }
  };

  const configureModel = async () => {
    setError(null);
    setNotice(null);
    setBusy('model');
    try {
      await agentFetch<unknown>(agentToken, 'market-research/install-model', { method: 'POST', body: {} });
      await load();
      setNotice('研究模型配置已写入本机研究服务。');
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(null);
    }
  };

  const reviewPrice = async () => {
    if (!price?.reviewable || !priceConfirmed) return;
    setError(null);
    setNotice(null);
    setBusy('price');
    try {
      const next = await agentFetch<ProviderStatus>(agentToken, 'provider/price-review', {
        method: 'POST',
        body: { confirmed: true, price_version: price.version },
      });
      setStatus(next);
      setPriceConfirmed(false);
      setNotice('DeepSeek 价格审核有效期已更新。');
      void agent.refresh();
    } catch (caught) {
      setError(friendlyError(caught));
    } finally {
      setBusy(null);
    }
  };

  const saved = status?.key_present === true;
  const showInput = !saved || editing || provider !== savedProvider;
  const modelInstalled = status?.model_installed === true;
  const priceState = price?.state === 'VALID' && price.valid_until !== null && Date.parse(price.valid_until) <= Date.now()
    ? 'EXPIRED' : price?.state;
  const canConfigureModel = status?.research_key_present === true && priceState === 'VALID' && !modelInstalled;

  const providerView = savedProvider === null
    ? statusView('unset', '未设置', '还没有连接 AI 服务')
    : statusView('ok', '已保存');
  const keyView = saved ? statusView('ok', '正常') : statusView('unset', '未设置');
  const modelView = modelInstalled && status?.research_key_present && priceState === 'VALID'
    ? statusView('ok', '已配置') : statusView('attention', '需要处理');
  const modelReason = modelInstalled
    ? '全市场研究配置固定使用 DeepSeek。实际启动由自动研究设置、数据授权和预算决定。'
    : '全市场研究使用 DeepSeek。保存 DeepSeek 密钥并确认价格后，可配置研究模型。';

  const agentBudget = agent.status?.budget ?? null;
  const budgetView = agentBudget === null
    ? statusView('progress', '进行中')
    : agentBudget.state === 'configured'
      ? statusView('ok', '正常')
      : statusView('attention', '需要处理', '尚未设置研究预算');
  const budgetText = agentBudget === null
    ? '正在读取研究预算'
    : agentBudget.state === 'configured'
      ? formatMicroMoney(agentBudget.daily_limit_micro, agentBudget.currency) + ' / 日 · ' + formatMicroMoney(agentBudget.monthly_limit_micro, agentBudget.currency) + ' / 月'
      : '未配置';

  return (
    <div className="provider-panel" data-testid="provider-panel">
      <h2 className="card__title">AI 服务</h2>
      <p className="provider-intro">
        OpenAI 仅支持保存密钥和测试连接。全市场研究使用独立的 DeepSeek 配置。
      </p>

      {error === null ? null : (
        <Callout tone="danger" title="未能完成" role="alert">
          {errorReason(error)}
          <Button variant="ghost" size="sm" disabled={busy !== null || loading} onClick={() => void load()}>重新读取配置</Button>
          <Diagnostics items={[{ label: '原始错误码', value: error.code }]} />
        </Callout>
      )}
      {notice === null ? null : <Callout tone="success" title="已完成">{notice}</Callout>}

      <div className="provider-status">
        <div className="provider-status__row">
          <span>已保存的连接测试服务</span>
          <div className="provider-status__value">
            {savedProvider === null ? null : <strong>{PROVIDER_LABELS[savedProvider] ?? ''}</strong>}
            <StatusBadge status={providerView} size="sm" />
          </div>
        </div>
        <div className="provider-status__row">
          <span>API Key</span>
          <div className="provider-status__value">
            <strong>{saved ? '已保存' : '未保存'}</strong>
            <StatusBadge status={keyView} size="sm" />
          </div>
          {saved ? <span>API Key 已保存在本机 Windows 凭据管理器。</span> : null}
        </div>
        <div className="provider-status__row">
          <span>全市场研究服务</span>
          <div className="provider-status__value">
            <strong>{status?.research_provider === 'deepseek' ? 'DeepSeek 官方' : '尚未配置研究模型'}</strong>
            <StatusBadge status={modelView} size="sm" />
          </div>
        </div>
        <div className="provider-status__row">
          <span>研究预算</span>
          <div className="provider-status__value">
            <strong>{budgetText}</strong>
            <StatusBadge status={budgetView} size="sm" />
            <BudgetEditor agent={agent} budget={agentBudget} />
          </div>
          {budgetView.reason === undefined ? null : <span>{budgetView.reason}</span>}
        </div>
      </div>

      <div className="provider-form">
        <Field label="选择要保存或测试的服务商" htmlFor="provider-name" hint="只支持官方端点。测试使用同一服务商的已保存密钥。">
          <SegmentedControl
            label="服务商"
            options={[
              { value: 'deepseek', label: 'DeepSeek' },
              { value: 'openai', label: 'OpenAI' },
            ]}
            value={provider}
            onChange={(next) => {
              setSelection(next);
              setKey('');
              setEditing(false);
              setNotice(null);
            }}
            disabled={loading || busy !== null}
          />
        </Field>

        {showInput ? (
          <Field label="API Key" htmlFor="provider-key" hint="以 sk- 开头；保存后页面只显示已保存状态。">
            <TextInput
              id="provider-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-…"
              value={key}
              onChange={(event) => {
                setSelection(provider);
                setKey(event.target.value);
              }}
              disabled={loading || busy !== null}
              data-testid="provider-key"
            />
          </Field>
        ) : (
          <p className="provider-note">API Key 已保存在本机 Windows 凭据管理器，页面不再显示密钥内容。</p>
        )}

        <div className="provider-actions">
          {showInput ? (
            <>
              <Button
                variant="secondary"
                loading={busy === 'save'}
                disabled={loading || key.trim() === '' || busy !== null}
                onClick={() => void save()}
                data-testid="provider-save"
              >
                保存密钥
              </Button>
              {saved ? (
                <Button
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => {
                    setEditing(false);
                    setKey('');
                    setSelection(null);
                  }}
                >
                  取消
                </Button>
              ) : null}
            </>
          ) : (
            <>
              <Button loading={busy === 'test'} disabled={loading || busy !== null} onClick={() => void test()} data-testid="provider-test">
                测试连接
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => setEditing(true)}>
                替换密钥
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="provider-steps">
        {price === null ? null : (
          <div className="provider-step">
            <div>
              <strong>DeepSeek 价格审核</strong>
              <p>{priceState === 'VALID' ? '有效至 ' + formatDateTime(price.valid_until ?? '')
                : priceState === 'EXPIRED' ? '已过期，付费研究暂停。' : '尚未确认，付费研究暂停。'}</p>
              <p>每百万 token 的计费上限为输入 {formatMicroMoney(price.input_micro_per_million, 'CNY')}、输出 {formatMicroMoney(price.output_micro_per_million, 'CNY')}。</p>
              <p><a href={price.source} target="_blank" rel="noreferrer">查看 DeepSeek 官方定价</a></p>
              {price.reviewable ? (
                <label className="budget-confirm__label">
                  <input type="checkbox" checked={priceConfirmed} disabled={busy !== null}
                    onChange={(event) => setPriceConfirmed(event.target.checked)} />
                  <span>我已核对当前价格，确认计费不超过上述上限</span>
                </label>
              ) : <p>请先保存本机 DeepSeek 密钥，再确认价格。</p>}
            </div>
            {price.reviewable ? (
              <Button size="sm" loading={busy === 'price'} disabled={!priceConfirmed || busy !== null}
                onClick={() => void reviewPrice()} data-testid="provider-price-review">
                确认价格，有效 7 天
              </Button>
            ) : null}
          </div>
        )}
        <div className="provider-step">
          <div>
            <strong>研究模型配置</strong>
            <p>{modelReason}</p>
          </div>
          {canConfigureModel ? (
            <Button size="sm" loading={busy === 'model'} disabled={busy !== null} onClick={() => void configureModel()} data-testid="provider-model-config">
              配置研究模型
            </Button>
          ) : null}
        </div>
      </div>

      {loading ? <p className="provider-note">正在读取 AI 服务配置…</p> : null}
      {status === null ? null : (
        <Diagnostics
          items={[
            { label: '服务代码', value: status.provider ?? '—' },
            { label: 'API Key 提示', value: status.key_hint ?? '—' },
            { label: '配置时间', value: status.configured_at === null ? '—' : formatDateTime(status.configured_at) },
            { label: 'HTTPS 端点', value: status.endpoint ?? '—' },
            { label: '研究模型已写入本机配置', value: status.model_installed ? 'true' : 'false' },
            { label: '研究预算原始记录', value: status.budget === null ? '—' : JSON.stringify(status.budget) },
            { label: '读取时本页研究预算', value: agentBudget === null ? '—' : JSON.stringify(agentBudget) },
          ]}
          data={status}
        />
      )}
    </div>
  );
}
