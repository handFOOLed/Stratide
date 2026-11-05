import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { Field, TextInput } from '../ui/Field';
import { SegmentedControl } from '../ui/SegmentedControl';
import { agentFetch, friendlyError } from '../../lib/api';
import { formatMicro } from '../../lib/format';
import { navigate } from '../../lib/route';

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
  model_installed: boolean;
  budget: Budget | null;
  endpoint: string | null;
}

const LABELS: Record<string, string> = { deepseek: 'DeepSeek 官方', openai: 'OpenAI 官方' };
const ENDPOINTS: Record<string, string> = {
  deepseek: 'https://api.deepseek.com',
  openai: 'https://api.openai.com/v1',
};

export function ProviderPanel() {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [provider, setProvider] = useState('deepseek');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await agentFetch<ProviderStatus>('', 'provider');
      setStatus(next);
      if (next.provider) setProvider(next.provider);
    } catch (caught) {
      setError(friendlyError(caught).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setError(null);
    setNotice(null);
    setBusy('save');
    try {
      const next = await agentFetch<ProviderStatus>('', 'provider', {
        method: 'POST',
        body: { provider, key },
      });
      setStatus(next);
      setKey('');
      setNotice('密钥已保存到 Windows 凭据管理器。');
    } catch (caught) {
      setError(friendlyError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setError(null);
    setNotice(null);
    setBusy('test');
    try {
      const result = await agentFetch<{ state: string; models?: number }>('', 'provider/test', {
        method: 'POST',
        body: {},
      });
      setNotice(
        result.state === 'OK'
          ? '连接成功，该密钥可访问 ' + String(result.models ?? 0) + ' 个模型。'
          : '连接结果：' + result.state,
      );
    } catch (caught) {
      setError(friendlyError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  const installModel = async () => {
    setError(null);
    setNotice(null);
    setBusy('model');
    try {
      await agentFetch<unknown>('', 'market-research/install-model', { method: 'POST', body: {} });
      await load();
      setNotice('研究模型已安装。');
    } catch (caught) {
      setError(friendlyError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="provider-panel">
      <h2 className="card__title">AI 服务</h2>
      <p className="provider-intro">
        连接云端研究模型。密钥只保存在 Windows 凭据管理器，不会写入文件、日志、页面源码或 Git。
      </p>

      {error ? (
        <Callout tone="danger" title="未能完成" role="alert">
          {error}
        </Callout>
      ) : null}
      {notice ? (
        <Callout tone="success" title="已完成">
          {notice}
        </Callout>
      ) : null}

      {status === null ? (
        <p className="muted">正在读取 AI 服务状态…</p>
      ) : (
        <div className="provider-status">
          <div className="provider-status__row">
            <span>当前服务</span>
            <strong>{status.provider ? LABELS[status.provider] ?? status.provider : '未配置'}</strong>
          </div>
          <div className="provider-status__row">
            <span>密钥</span>
            <strong>{status.key_present ? '已保存（凭据管理器）' : '未保存'}</strong>
          </div>
          <div className="provider-status__row">
            <span>研究模型</span>
            <strong>{status.model_installed ? '已安装' : '未安装'}</strong>
          </div>
          <div className="provider-status__row">
            <span>预算</span>
            <strong>
              {status.budget
                ? '¥' + formatMicro(status.budget.daily_limit_micro) + ' / 日 · ¥' +
                  formatMicro(status.budget.monthly_limit_micro) + ' / 月'
                : '未配置'}
            </strong>
          </div>
        </div>
      )}

      <div className="provider-form">
        <Field label="服务商" htmlFor="provider-name" hint="只接受官方 HTTPS 端点。">
          <SegmentedControl
            label="服务商"
            options={[
              { value: 'deepseek', label: 'DeepSeek' },
              { value: 'openai', label: 'OpenAI' },
            ]}
            value={provider}
            onChange={setProvider}
          />
        </Field>
        <Field
          label="API Key"
          htmlFor="provider-key"
          hint={ENDPOINTS[provider] + ' · 保存后不再回显'}
        >
          <TextInput
            id="provider-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="sk-…"
            value={key}
            onChange={(event) => setKey(event.target.value)}
          />
        </Field>
        <div className="provider-actions">
          <Button variant="primary" loading={busy === 'save'} disabled={key.trim() === ''} onClick={() => void save()}>
            保存密钥
          </Button>
          <Button loading={busy === 'test'} disabled={!status?.key_present} onClick={() => void test()}>
            测试连接
          </Button>
        </div>
      </div>

      {status?.key_present ? (
        <div className="provider-steps">
          <div className="provider-step">
            <div>
              <strong>1. 安装研究模型</strong>
              <p className="muted">把已保存的服务商配置接入研究运行时；可重复执行。</p>
            </div>
            <Button size="sm" loading={busy === 'model'} onClick={() => void installModel()}>
              {status.model_installed ? '重新安装' : '安装'}
            </Button>
          </div>
          <div className="provider-step">
            <div>
              <strong>2. 授权数据外发</strong>
              <p className="muted">只有你明确同意后，行情摘要才会发送到该服务商；可随时撤回。</p>
            </div>
            <Button size="sm" variant="secondary" onClick={() => navigate({ page: 'settings', section: 'security' })}>
              前往授权
            </Button>
          </div>
        </div>
      ) : null}

      {provider === 'openai' ? (
        <p className="provider-note">
          OpenAI 密钥可保存并测试连接；当前版本的自动市场研究固定使用 DeepSeek 融合模型。
        </p>
      ) : null}
      <p className="provider-note">
        自动研究还要求行情累计满 84 个交易日，并通过风控与预算检查；本页不提升预算、不授予交易权限。
      </p>
    </div>
  );
}
