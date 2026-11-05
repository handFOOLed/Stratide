import { useState } from 'react';
import { Button } from '../ui/Button';
import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { Field, TextInput } from '../ui/Field';
import { Modal } from '../ui/Overlay';
import { useToast } from '../ui/Toast';
import { ApiError, friendlyError, updateAgentBudget } from '../../lib/api';
import { formatMicroMoney, parseInteger } from '../../lib/format';
import { failureReasonText, humanReasonText } from '../../lib/status';
import type { AgentBudget, AgentBudgetUpdateRequest } from '../../lib/types';
import type { AgentState } from '../../state/useAgent';

const MICRO_PER_UNIT = 1_000_000n;
const MICRO_PER_CENT = 10_000n;

/** 预算保存错误码 → 一句人话；原始码只进诊断信息。 */
const BUDGET_ERROR_TEXT: Record<string, string> = {
  BUDGET_BELOW_COMMITTED: '预算已变化：新上限低于已结算或未结预留的费用，请重新确认后再保存。',
  BUDGET_INPUT_INVALID: '预算金额格式不正确，请检查每日与每月上限。',
  BUDGET_CONFLICT_REREAD: '预算已在别处修改，请重新读取后再试。',
  BUDGET_CONFIG_INVALID: '本机研究配置不可读或写入失败，请检查本机研究目录后重试。',
  BUDGET_CURRENCY_TIMEZONE_IMMUTABLE: '币种与时区在首次设置后不能修改。',
  AGENT_STORAGE_UNAVAILABLE: '本机研究配置保存失败，请检查本机目录写入权限。',
  OWNER_TOKEN_REQUIRED: '本机会话已失效，请重新打开页面。',
};

function budgetErrorText(error: ApiError): string {
  const known = BUDGET_ERROR_TEXT[error.code];
  if (known !== undefined) return known;
  const message = humanReasonText(error.message);
  if (message !== null && message !== '—') return message;
  return failureReasonText(error.code);
}

/** micro 货币 → 两位小数的金额输入值。 */
function microToInput(value: string | null): string {
  const micro = parseInteger(value);
  if (micro === null || micro <= 0n) return '';
  const whole = micro / MICRO_PER_UNIT;
  const cents = (micro % MICRO_PER_UNIT + MICRO_PER_CENT / 2n) / MICRO_PER_CENT;
  if (cents === 100n) return (whole + 1n).toString() + '.00';
  return whole.toString() + '.' + cents.toString().padStart(2, '0');
}

/** 金额输入 → micro 字符串；要求大于 0 且最多两位小数。 */
function inputToMicro(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ''] = trimmed.split('.');
  return (BigInt(whole) * MICRO_PER_UNIT + BigInt(fraction.padEnd(2, '0')) * MICRO_PER_CENT).toString();
}

function committedMicro(settled: string | null, reserved: string | null): string | null {
  const settledValue = parseInteger(settled);
  const reservedValue = parseInteger(reserved);
  if (settledValue === null || reservedValue === null) return null;
  return (settledValue + reservedValue).toString();
}

/**
 * 研究预算编辑：日/月上限按元（CNY 显示 ¥，其他币种显示代码）输入，换算为 micro。
 * AI 研究页与设置页共用；保存成功后刷新共享的 agent 状态。
 */
export function BudgetEditor({
  agent,
  budget,
  disabled = false,
}: {
  agent: AgentState;
  budget: AgentBudget | null;
  disabled?: boolean;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [dailyInput, setDailyInput] = useState('');
  const [monthlyInput, setMonthlyInput] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const configuredBudget = budget !== null && budget.state === 'configured' ? budget : null;
  const currency = configuredBudget === null ? 'CNY' : configuredBudget.currency;
  const timezone = configuredBudget === null ? 'Asia/Shanghai' : configuredBudget.timezone;
  const currencyPrefix = currency === 'CNY' ? '¥' : currency;
  const amountHint = currency === 'CNY' ? '金额以元输入，最多两位小数。' : '金额以币种单位输入，最多两位小数。';

  const dailyMicro = inputToMicro(dailyInput);
  const monthlyMicro = inputToMicro(monthlyInput);
  const dailyValue = dailyMicro === null ? null : BigInt(dailyMicro);
  const monthlyValue = monthlyMicro === null ? null : BigInt(monthlyMicro);
  const formValid =
    dailyValue !== null &&
    monthlyValue !== null &&
    dailyValue > 0n &&
    monthlyValue > 0n &&
    dailyValue <= monthlyValue;

  const dailyCommitted =
    configuredBudget === null ? null : committedMicro(configuredBudget.daily_settled_micro, configuredBudget.reserved_micro);
  const monthlyCommitted =
    configuredBudget === null ? null : committedMicro(configuredBudget.monthly_settled_micro, configuredBudget.reserved_micro);
  const dailyBelow =
    dailyCommitted !== null && dailyValue !== null && dailyValue > 0n && dailyValue < BigInt(dailyCommitted);
  const monthlyBelow =
    monthlyCommitted !== null && monthlyValue !== null && monthlyValue > 0n && monthlyValue < BigInt(monthlyCommitted);
  const requiresConfirm = dailyBelow || monthlyBelow;

  let validationMessage: string | null = null;
  if (dirty) {
    if (dailyInput.trim() === '' || monthlyInput.trim() === '') {
      validationMessage = '请填写每日上限与每月上限。';
    } else if (dailyValue === null || monthlyValue === null || dailyValue <= 0n || monthlyValue <= 0n) {
      validationMessage = '请输入大于 0 的金额，最多两位小数。';
    } else if (dailyValue > monthlyValue) {
      validationMessage = '每日上限不能高于每月上限。';
    }
  }

  const canSubmit = formValid && (!requiresConfirm || confirmed) && !submitting;

  const startEdit = () => {
    setDailyInput(microToInput(configuredBudget === null ? null : configuredBudget.daily_limit_micro));
    setMonthlyInput(microToInput(configuredBudget === null ? null : configuredBudget.monthly_limit_micro));
    setConfirmed(false);
    setDirty(false);
    setError(null);
    setOpen(true);
  };

  const close = () => {
    if (!submitting) setOpen(false);
  };

  const submit = async () => {
    if (!formValid || dailyMicro === null || monthlyMicro === null) return;
    if (requiresConfirm && !confirmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const request: AgentBudgetUpdateRequest = {
        daily_limit_micro: dailyMicro,
        monthly_limit_micro: monthlyMicro,
        confirm_below_committed: requiresConfirm,
      };
      if (configuredBudget === null) {
        // 首次设置时确定币种与时区；之后由服务端锁定，不能修改。
        request.currency = currency;
        request.timezone = timezone;
      }
      await updateAgentBudget(agent.token ?? 'local', request);
      toast.push({
        title: '预算已更新',
        description: '每日与每月上限已保存，新的研究按新上限执行。',
        tone: 'success',
      });
      setOpen(false);
      await agent.refresh({ silent: true });
    } catch (caught) {
      const failure = friendlyError(caught);
      setError(failure);
      if (failure.code === 'BUDGET_BELOW_COMMITTED' || failure.code === 'BUDGET_CONFLICT_REREAD') {
        void agent.refresh({ silent: true });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDetails: string[] = [];
  if (dailyBelow && dailyCommitted !== null) {
    confirmDetails.push('今日已结算与未结预留合计 ' + formatMicroMoney(dailyCommitted, currency) + '。');
  }
  if (monthlyBelow && monthlyCommitted !== null) {
    confirmDetails.push('本月已结算与未结预留合计 ' + formatMicroMoney(monthlyCommitted, currency) + '。');
  }

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        icon="settings"
        onClick={startEdit}
        disabled={disabled}
        data-testid="budget-edit"
      >
        编辑预算
      </Button>
      <Modal
        open={open}
        onClose={close}
        title="编辑研究预算"
        description="预算只限制付费研究；达到上限后只会暂停新的研究，不影响行情采集与交易保护。"
        wide
        footer={
          <>
            {requiresConfirm && !confirmed ? <span className="modal__foot-note">请先勾选确认项再保存。</span> : null}
            <Button variant="ghost" type="button" onClick={close} disabled={submitting}>
              取消
            </Button>
            <Button
              variant="primary"
              type="submit"
              form="budget-form"
              loading={submitting}
              disabled={!canSubmit}
              data-testid="budget-save"
            >
              保存预算
            </Button>
          </>
        }
      >
        <form
          id="budget-form"
          className="budget-editor"
          data-testid="budget-editor"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="budget-editor__grid">
            <Field label="每日上限" htmlFor="budget-daily" hint={amountHint}>
              <div className={'budget-input' + (currency === 'CNY' ? '' : ' budget-input--code')}>
                <span className="budget-input__prefix" aria-hidden="true">{currencyPrefix}</span>
                <TextInput
                  id="budget-daily"
                  data-testid="budget-daily"
                  data-autofocus
                  inputMode="decimal"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="0.00"
                  value={dailyInput}
                  disabled={submitting}
                  onChange={(event) => {
                    setDirty(true);
                    setDailyInput(event.target.value);
                  }}
                />
              </div>
            </Field>
            <Field label="每月上限" htmlFor="budget-monthly" hint={amountHint}>
              <div className={'budget-input' + (currency === 'CNY' ? '' : ' budget-input--code')}>
                <span className="budget-input__prefix" aria-hidden="true">{currencyPrefix}</span>
                <TextInput
                  id="budget-monthly"
                  data-testid="budget-monthly"
                  inputMode="decimal"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="0.00"
                  value={monthlyInput}
                  disabled={submitting}
                  onChange={(event) => {
                    setDirty(true);
                    setMonthlyInput(event.target.value);
                  }}
                />
              </div>
            </Field>
          </div>

          {configuredBudget === null ? null : (
            <p className="budget-editor__current">
              当前上限：{formatMicroMoney(configuredBudget.daily_limit_micro, currency)} / 日 ·{' '}
              {formatMicroMoney(configuredBudget.monthly_limit_micro, currency)} / 月
            </p>
          )}
          <p className="budget-editor__note">每日与每月额度按 {timezone} 重置；保存后立即生效。</p>

          {validationMessage === null ? null : (
            <p className="budget-editor__error" role="alert">{validationMessage}</p>
          )}

          {requiresConfirm ? (
            <div className="budget-confirm">
              <label className="budget-confirm__label" htmlFor="budget-confirm-below">
                <input
                  id="budget-confirm-below"
                  data-testid="budget-confirm-below"
                  className="budget-confirm__checkbox"
                  type="checkbox"
                  checked={confirmed}
                  disabled={submitting}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>降到已用/预留以下后，新的研究会被阻止</span>
              </label>
              {confirmDetails.length === 0 ? null : (
                <p className="budget-confirm__detail">{confirmDetails.join(' ')}</p>
              )}
            </div>
          ) : null}

          {error === null ? null : (
            <Callout tone="danger" title="预算未更新" role="alert">
              {budgetErrorText(error)}
              <Diagnostics
                items={[
                  { label: '错误代码', value: error.code },
                  { label: '错误信息', value: error.message === '—' ? '原因未记录' : error.message },
                  { label: 'HTTP 状态', value: String(error.status) },
                ]}
                data={{ code: error.code, status: error.status, detail: error.detail }}
              />
            </Callout>
          )}
        </form>
      </Modal>
    </>
  );
}
