# PR #8 补测后整改：Owner 声明确认与真实行情入 journal

日期：2026-10-28（Asia/Taipei）。**Sol 配置与实测补充，不是独立验收 PASS。** 实测生产代码仍为 `f801dd57e3e8605d51404008dd229a221e11585c`；本次提交只更新文档和脱敏证据，未修改 Rust、Cargo、默认样例配置或既有账本。后续验收须绑定 PR 届时准确 HEAD。

## 补测意见如何处理

[原补测报告](https://github.com/handFOOLed/Stratide/pull/8#issuecomment-6468480137)没有提出新的源码缺陷；86 项回归及许可阻断路径通过，缺口是来源许可依据、独立本地 HTTP 复现和真实响应入库。报告自身明确未证明 ADR-037 指定的 Terra 身份门槛，不在本记录中替它升级身份或结论。

Owner 在本次整改对话回答了“本账户自动 daily/trade_cal 采集、在个人本机长期保存原始响应、非商业 Paper 观察是否获准”的范围问题，明确确认允许，并说明当前账户可调用 2000 积分权限接口。**这项依据的来源是 Owner 声明，不是供应商书面许可、账户后台积分审计或独立合规认证。** 公开协议与第三方数据限制仍见 [来源报告](../../M1_PR04A_SOURCE_FEASIBILITY.md)；是否足以满足正式来源许可门槛，交由后续独立验收及 Owner/最终审查判定，不能由本次成功取数自动认证。

据此创建新的本地配置及 journal：`state/pr04a-owner-authorized-config.json`、`state/pr04a-owner-authorized-20261028`。genesis 记录该 Owner 声明、用途、本地保存范围和实际开始时间 `2026-10-28T20:09:58.396+08:00`。旧 `state/pr04a-owner-observer` 保持原 5 事件、2 次失败和原 HEAD；未修改历史 false 配置或开始时间。默认随仓样例仍为 false，不把此次个人声明扩展为所有用户已获许可。

## 本机实际执行

使用 Owner 先前明确为本任务提供的 Token，仅放在进程环境，finally 清除。没有将凭证落盘、复制其他项目配置、发给验收者或上传 GitHub。原始响应及带价格的报告只在本机，不提交云仓库。

```text
forward-init state/pr04a-owner-authorized-20261028 state/pr04a-owner-authorized-config.json
  exit=0; 新 genesis，不是恢复或改写 blocked 观察
forward-collect-once state/pr04a-owner-authorized-20261028
  exit=0; valid_eod; trade_day=20261028
新进程 forward-status、forward-report ... state/pr04a-real-first-report
  exit=0; 原始响应已由真实 HTTPS 采集并持久写入，非 MCP 导入
forward-collect-once state/pr04a-owner-authorized-20261028
  exit=0; valid_eod; duplicate_of=2，原事件保持
forward-collect-once state/pr04a-owner-authorized-20261028 --trade-day 20261027
  exit=0; valid_eod; late_backfill=true，实际可得时刻为今天
新进程 forward-status、forward-report ... state/pr04a-real-final-report
  exit=0; 同 HEAD 报告重复导出 exit=0
```

| 真实尝试 | 取得/可得时间（+08:00） | 证据与计数 |
| --- | --- | --- |
| 当日首次 | 20:10:14.443 开始；日历 20:10:15.611 收到，日线 20:10:16.933 收到；available 20:10:16.934 | seq=2；计一个当日前向日 |
| 当日再次 | 20:10:44.014 开始；available 20:10:53.705 | seq=4；duplicate_of=2；有效日数不增加 |
| 昨日今日首取 | 20:10:53.729 开始；available 20:10:57.603 | seq=6；trade_day=20261027、late_backfill=true；不计第二个前向日 |

这些均为 2026-10-28 的真实本地时刻，不是把昨日数据回填成昨日已知。证券为 `600000.SH`，日历为 SSE；全部是实际本地 CLI 的 Tushare HTTPS 响应。每次仅一次日历加一次日线请求，共 6 次小请求，不存在自动轮询、付费购买或真实订单。

最终 journal HEAD：`b7ba4a86e05c8ce3cf71c755afa8e7db2ff31fd3056b8b2ff6d12c610c084f52`。新进程恢复后为 **7 事件、3 尝试、1 有效前向日、0 提案、0 成交、0 挂起 run**；NAV/回撤仍 unavailable。`provider_published_at=null`，available 不早于实际接收时刻。这里的“有效”是程序结构/字段/粗粒度时钟检查结果，不是策略盈利或独立证据资格认证。

## 原始证据核对

用 Python 标准库只读打开 SQLite（`mode=ro`），按数据库原 payload 字节的规范序列重算整条 SHA-256 链和尾标；对 6 个 raw.body 分别重算 SHA-256，使用 Decimal 核对真实原始 OHLC×100=整数分、vol×100=整数股，核对证券/交易日和 available≥received。核对旧 seq=2 摘要仍与首次报告 HEAD 一致、第二次指向原 seq=2、昨日补录 late 标记，以及最终状态/报告。

上述本机核对全部通过；脚本为本地 `state/verify-pr04a-real.py`，输出经过字段白名单限制，只提交 [real-collection-metadata.json](real-collection-metadata.json)。文件包含各响应哈希、接收时刻和报告文件哈希，不含原始或标准化价格、成交量、Token、账号标识或原始消息。由于原始数据未上传，远端读者不能仅靠这份元数据离线复算 raw；独立验收仍需在有权限的本机运行：

```powershell
# 不需要 Token：恢复和报表只读已有 journal，不再请求网络
./target/debug/stratide-cli.exe forward-status state/pr04a-owner-authorized-20261028
./target/debug/stratide-cli.exe forward-report state/pr04a-owner-authorized-20261028 state/pr04a-independent-report
python state/verify-pr04a-real.py
```

验收者若需重新采集，须在 Owner 已授权的本机进程环境中配置凭证；清除环境变量是凭证保护措施，不能通过把 Token 写入 Git 或长期留在共享环境来“修复”。本轮解决了缺少真实入库实证的问题，没有声称验收者已独立重复该 HTTP 采集。

## 尚未通过的门槛

- 来源使用依据目前为 Owner 明确声明；供应商书面确认、第三方权利方独立确认和正式许可验收仍未证明，不能将两者混称。
- 尚无两个真实未来交易日。当天重复和昨日今日补录不能满足此项；后续实际新交易日再采集，不能预先生成。
- Terra 规定身份的同 SHA 独立验收及小猫最终源码审查未完成，PR 保持 Draft，不合并。
- 真实限流、休市/停牌、源修订现场、Linux/macOS、物理断电/磁盘满、独立开盘/费用/时段证据仍未验证；不生成 paper 买卖。

生产代码未变，因此未为纯文档证据更新重复运行 86 项合成回归；原 Sol 自测和补测的固定代码结果完整保留。本轮新增验证是实际 HTTPS 入库、新进程恢复、真实重复/晚到行为、原始哈希/数值守恒、不可覆盖报告和旧 blocked 证据保持。
