# M2-PR17 开发者证据

Base `e24f30f69b12fa303221ccd4fc6b8ea9084dc989`，2026-11-03，Windows x64，单人、0 子代理。实现和启动步骤见 [M2_PR17](../../M2_PR17.md)。这是开发者自测，独立验收 `NOT_VERIFIED`；不自行 Ready/merge。

本次真实状态：**`REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING`**。Owner 未提供具体 CNY 费用预算与 DeepSeek 纯合成外发批准；真实密钥正文读取 **0**，真实 Provider HTTPS **0**，实际付费 **0**，真实行情/派生摘要外发 **0**。未读取 Tushare Token、未新增行情请求、未重验旧 raw/全库、未重跑旧两轮五年研究。安装 Skill 的文档与公开协议查阅不属于行情 API 请求。

## 命令和退出码

在本期 worktree 根执行。Windows Rust 命令前使用 `TEMP=TMP=<worktree>/state/rust-temp`，沿用已有 MSVC；未安装工具链、未触发付费 CI。

| 实际命令 | exit | 结果 |
| --- | ---: | --- |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 build --locked -p stratide-research --bin structured-research-agent -p stratided --bin stratided` | 0 | 真实生产二进制构建成功 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 test --locked -p stratide-research -- --test-threads=1` | 0 | 67 PASS：26 lib + 2 CLI + 39 原 Agent/Budget/状态/路由 integration |
| `python -I -B scripts/test-deepseek-structured.py` | 0 | 5 PASS，包含 5 种内容异常子例及本机离线评价、未知用量、只读审计、原发票核销 |
| `python -I -B scripts/test-cloud-structured.py` | 0 | 9 PASS，原 PR16 recorded/loopback、四 AST、预算/撤销/失败/篡改/开发反馈 |
| `python -I -B scripts/test-autonomous-research.py` | 0 | 14 PASS，原 PR15 受限 AST、Decimal/成本、冻结、恢复、post-seal 和只读控制 |
| `python -I -B scripts/test-multistock-research.py` | 0 | 12 PASS，原 PR62 费用/时点/缺失/仓位/复权/确定性/只读边界 |
| `python -I -B scripts/run-deepseek-evidence.py --tag issue67-final` | 0 | 1 次 loopback、4 合成 AST → 原 PR62、verify=true、重复 once 仍只有 1 个调用 |
| `cargo fmt --all -- --check` | 0 | Rust 格式通过 |
| `git diff --check` | 0 | 补丁空白检查通过 |

构建出现 incremental cache hard-link 不可用、改为复制的 Windows 警告，退出码为 0。过程中曾因 Rust 重建正在被 Python 使用的 exe 发生文件锁冲突，改为先完成 Rust 构建再运行 Python；新测试还修正了 SQLite context manager 不关闭连接造成的清理错误。最终命令正常退出，不把中途失败记为 PASS。

## 先红后绿

具体安全反例 `structured_tests::deepseek_https_cannot_accept_an_unapproved_receiver`：将 structured 模型传输设为 HTTPS、model 为 `deepseek-flash`、接收方为合成的 `https://unapproved.example/chat/completions`，只调用配置校验，**无 DNS/HTTP**。

```text
原 main 代码 + 新测试：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 test --locked -p stratide-research --lib structured_tests::deepseek_https_cannot_accept_an_unapproved_receiver -- --exact --nocapture
exit 1
FAILED: an HTTPS structured model must be restricted to the approved DeepSeek receiver
0 passed; 1 failed

修复固定 model/ID/receiver 后，同一命令：
exit 0
1 passed; 0 failed
最终 67 项原 Agent 回归中该反例继续 PASS。
```

## 高风险行为覆盖

| 边界 | 具体执行证据 |
| --- | --- |
| 默认 OFF / 未授权先拒绝 | 原 CNY 测试 Store，未 enable；即便 Key 文件正文是故意非法内容，仍先报一次授权缺失/关闭，0 calls；metadata-only preflight 不读正文 |
| 密钥文件 | 临时 Git 中 unignored 拒绝、ignored 允许元数据检查、tracked 拒绝；单 Key 解析，重复/占位/其他凭据拒绝；Provider 反射 Key 只留静态拒绝原因 |
| 正式 wire | libtest 使用真实请求生成和同一 `provider::send`：model=deepseek-flash、thinking disabled、json_object、max_tokens=4096、无 tools/functions；Authorization 是合成凭据，检查过程不输出其值 |
| 纯 synthetic / Source | 合成投影精确匹配；额外账户字段、非 SHA parser、伪造 source/model、未知字段/重复 key/非有限/越权/脚本被拒绝；真实数据版本/日期/反馈不进入请求 |
| 原 CNY 费用权威 | 峰值全 miss 最大 98,304 micro；usage 估算与 invoice 分开，`usage_received` 不释放最大预留；不接受 TST 转真实，低价/过期价拒绝；预算不足先于 Key 正文/DNS |
| final dispatch | after_reserve 窄故障：disable、Grant revoke、取消、原全局 pause、降预算和变更请求 SHA 全部 no_charge，无发送；开关和 dispatch 原子消耗 |
| 无重复 POST | 重复 once 读取相同 task ID/trigger；Provider 超时/断开/429/500、usage 缺失、模型伪造、reasoning 越界、token overrun/进程崩溃不再次 POST |
| 未知跨期 | dispatched 崩溃重启为 outcome_uncertain，最大预留跨日/月保留；unknown 审计显示 possible call，external_data_sends 未知，不能宣称 0 外发 |
| 200 空白/截断/拒答 | 完整 usage 保留估算，PR15 拒绝候选并封存；部分合法候选可评价，不补足、不重试，0 合法候选也允许归档 |
| 原研究闭环 | 4 个结构不同合成 AST 经唯一 PR15 validator 冻结；原 PR62 同源/三成本/基准本机评价；verify 和重放通过；原发票核销不改签 frozen archive |
| 只读和状态 | 删除合成 Key 后 `status/history/report/verify` 正常，不开源库或 Agent；loopback 始终 `LOOPBACK_NOT_REAL_PROVIDER`，原 Store/Agent 不标真实调用成功；旧 PR56/structured recorded 及 fake 回归保留 |

## 可检查的单次合成运行

[synthetic-result.json](synthetic-result.json) 保存合成 source/plan/model/prompt/parser/binary、request/task/AST/result/archive SHA、原调用状态和去敏 usage。所有预算、Grant、时间及金额均来自 disposable **CNY 测试 fixture**，不代表 Owner 真实费用授权。未提交凭据 locator、完整 wire、Key、真实行情或真实 Provider 响应。

```text
preflight.enabled=false → 显式 enable → 1 次本机 loopback
input/output tokens=4096/4096
maximum_micro=98304, usage_micro=40960, settled_micro=0
state=usage_received，完整最大预留仍保留
accepted=4, rejected=0, verify=true
after_once.enabled=false，重复 once 后 calls=1
real_provider_calls=0, actual_paid_calls=0, actual_paid_micro=0
```

完整合成档案保存在 ignored `state/`；可用上表生成器换一个 tag 再生成独立 fixture。原真实 V1/V2/实验/报告未参与本次运行，旧冻结证据不改签。

结果固定 `EXPLORATORY_EX_POST / REUSED_EXPOSED_PERIOD`、`PIT NOT_VERIFIED`、`forward_research_readiness=BLOCKED`、`ELIGIBILITY_DENIED`、`paper_allowed=false`、`live_allowed=false`。真实网络/账单/策略质量、Linux/macOS 和独立验收均未获证；合成工程 PASS 不认证盈利或交易准入。
