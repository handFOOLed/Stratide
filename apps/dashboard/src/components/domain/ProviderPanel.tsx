import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { Field, TextInput } from '../ui/Field';
import { SegmentedControl } from '../ui/SegmentedControl';
import { agentFetch, friendlyError } from '../../lib/api';
import { formatMicro } from '../../lib/format';

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
  budget: Budget | null;
  endpoint: string | null;
}

const LABELS: Record<string, string> = { deepseek: 'DeepSeek 官方', openai: 'OpenAI 官方' };

export function ProviderPanel() {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [provider, setProvider] = useState('deepseek');
  const [key, setKey] = useState('');
  const [editing, setEditing] = useState(false);
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
      setEditing(false);
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

  const saved = status?.key_present === true;
  const showInput = !saved || editing;

  return (
    <div className="provider-panel">
      <h2 className="card__title">AI 服务</h2>

      {error ? (
        <Callout tone="danger" title="未能完成" role="alert">
          {error}
        </Callout>
      ) : null}
      {notice ? <Callout tone="success" title="已完成">{notice}</Callout> : null}

      <div className="provider-status">
        <div className="provider-status__row">
          <span>当前服务</span>
          <strong>{status?.provider ? LABELS[status.provider] ?? status.provider : '未配置'}</strong>
        </div>
        <div className="provider-status__row">
          <span>API Key</span>
          <strong>{saved ? status?.key_hint ?? '已保存' : '未保存'}</strong>
        </div>
        <div className="provider-status__row">
          <span>研究模型</span>
          <strong>{status?.model_installed ? '已安装' : '未安装'}</strong>
        </div>
        <div className="provider-status__row">
          <span>预算</span>
          <strong>
            {status?.budget
              ? '¥' + formatMicro(status.budget.daily_limit_micro) + ' / 日 · ¥' +
                formatMicro(status.budget.monthly_limit_micro) + ' / 月'
              : '未配置'}
          </strong>
        </div>
      </div>

      <div className="provider-form">
        <Field label="服务商" htmlFor="provider-name">
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

        {showInput ? (
          <Field label="API Key" htmlFor="provider-key">
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
        ) : (
          <Field label="API Key" htmlFor="provider-key-saved">
            <TextInput id="provider-key-saved" value={status?.key_hint ?? ''} readOnly disabled />
          </Field>
        )}

        <div className="provider-actions">
          {showInput ? (
            <>
              <Button
                variant="primary"
                loading={busy === 'save'}
                disabled={key.trim() === ''}
                onClick={() => void save()}
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
                  }}
                >
                  取消
                </Button>
              ) : null}
            </>
          ) : (
            <>
              <Button loading={busy === 'test'} onClick={() => void test()}>
                测试连接
              </Button>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                替换密钥
              </Button>
            </>
          )}
        </div>
      </div>

      {saved ? (
        <div className="provider-steps">
          <div className="provider-step">
            <div>
              <strong>研究模型</strong>
            </div>
            <Button size="sm" loading={busy === 'model'} onClick={() => void installModel()}>
              {status?.model_installed ? '重新安装' : '安装'}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
