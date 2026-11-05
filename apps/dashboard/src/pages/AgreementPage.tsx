import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { acceptConsent } from '../lib/consent';

const SECTIONS: Array<{ title: string; body: string }> = [
  {
    title: '只在本机、只做模拟',
    body: '软件运行在 127.0.0.1，不连接券商、不能下真实订单。所有成交都是模拟假设，不是真实交易。',
  },
  {
    title: '模拟账户',
    body: '开户即使用 ¥100,000 模拟本金，最多同时持有 2 只，单票上限 ¥20,000。日亏损 2% 或回撤 10% 会自动阻止新的模拟下单。',
  },
  {
    title: '云端研究',
    body: '当你启用 AI 服务后，会把最多 8 个证券、84 个交易日的行情摘要、风险预测与研究契约字段发送给 DeepSeek 官方（api.deepseek.com），仅用于策略研究，有效期 10 年。不会发送账户余额、真实持仓、账本、密钥或原始行情文件。',
  },
  {
    title: '费用上限',
    body: '云端调用硬上限为 ¥5/日、¥100/月。超出即暂停研究，不影响行情采集与风控。',
  },
  {
    title: '行情数据',
    body: 'Tushare 数据按个人本地许可使用，只在本机保存与计算，不转发、不再分发。',
  },
  {
    title: '密钥与安全',
    body: 'API Key 只保存在 Windows 凭据管理器；页面不回显，日志不记录。',
  },
  {
    title: '风险提示',
    body: '模拟成交与历史回测不代表未来收益，也不构成投资建议。软件不保证盈利，也不保证最大亏损。',
  },
  {
    title: '如何停止',
    body: '删除数据目录里的 runtime/consent.json 即停止新的云端研究；卸载默认保留数据目录。',
  },
];

export function AgreementPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      await acceptConsent();
      window.location.reload();
    } catch {
      setError('保存失败，请确认本机服务正在运行后重试。');
      setBusy(false);
    }
  };

  return (
    <div className="agreement">
      <div className="agreement__card">
        <p className="agreement__eyebrow">Stratide · 首次使用</p>
        <h1 className="agreement__title">开始之前，只有这一页</h1>
        <p className="agreement__lead">
          这是一份一次性的说明与授权。同意后，软件不会再弹出任何许可或审批。
        </p>
        <div className="agreement__sections">
          {SECTIONS.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </section>
          ))}
        </div>
        {error ? (
          <Callout tone="danger" title="没有保存成功">
            {error}
          </Callout>
        ) : null}
        <div className="agreement__actions">
          <Button variant="primary" size="lg" loading={busy} onClick={() => void accept()}>
            同意并继续
          </Button>
          <span className="agreement__hint">同意记录只保存在本机，不会上传。</span>
        </div>
      </div>
    </div>
  );
}
