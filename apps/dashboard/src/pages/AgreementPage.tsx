import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { acceptConsent } from '../lib/consent';

const SECTIONS: Array<{ title: string; body: string }> = [
  {
    title: '只做模拟',
    body: '软件只在这台电脑上运行，不连接券商，不能下真实的单。模拟成交和盈亏不代表真实赚钱。',
  },
  {
    title: '模拟账户',
    body: '起始资金 ¥100,000。最多同时持有 2 只股票，单只最多 ¥20,000。当天亏损达到 2%，或从高点回撤达到 10%，就停止新的模拟下单。',
  },
  {
    title: '研究会发出去什么',
    body: '全市场研究最多带 8 只股票、84 个交易日的行情摘要，以及本机风险预测，发到 api.deepseek.com，只用于研究。不发送账户余额、真实持仓、成交账本、密钥，也不发送原始行情文件。',
  },
  {
    title: '费用有上限',
    body: '云端研究每天最多 ¥5，每月最多 ¥100。到顶就停止新的研究，不影响本机行情和交易保护。',
  },
  {
    title: '行情密钥留在本机',
    body: 'Tushare 密钥只在这台电脑上使用，不转发给云端。密钥放在 Windows 凭据管理器里，页面不显示，日志也不记录。',
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
        <h1 className="agreement__title">使用前请先看这几条</h1>
        <p className="agreement__lead">点一次「同意并继续」，这页就不会再出现。</p>
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
