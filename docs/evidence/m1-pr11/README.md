# M1-PR11 开发自测证据

基线 `main 1b2c9033946e1cb4dc9079115837f3d1c11d21ca`（PR #52 已合并）。一个 Draft PR，`agents=0`；审查用固定 HEAD 在 PR 描述。Windows x64 / Python 3.12 / 现有 Rust + MSVC。这里是开发者自测，独立验收仍 **NOT_VERIFIED**。

## 真实结果：BLOCKED

[real-audit.json](real-audit.json) 来自实际生产 CLI 的 `init → audit → status/verify/report`。外层测试退出 0 表示拒绝和保全均符合预期；内层 audit/query 均退出 **2 / BLOCKED**。

- 原真实 `forward_observed_eod` 仍只有 `20261028/29` 两个有效日、5 事件、4 raw；原 PR33 SHA 为 `3def7bf43e54d889a68db292b09cfe0885782f650438792b01baff70f44cde03`。没有重新采集或 sync 原 store。
- 缺少独立事件源按时完整覆盖且快照过期，明确返回七项 blocker。新真实审计 receipt SHA 为 `dd0e0762b516b8d9f3dabc90e8901d23910110dc22024f49437cbdaa2708d22e`。
- 原 PR38 `FACTS_PARTIAL`、事后取得时间、公告/原文 SHA 和未核实 PIT 保留；PR40 模型通过不赋予真实来源权威。
- [preservation.json](preservation.json)：原 observer、PR33 store 和 PR38 包 **14/14** 文件前后 SHA + mtime 相同。4 个 raw payload 和新 receipt 的 SHA 通过独立 `hashlib` 重新计算，未只信任 receipt 自报字段。
- [source-permissions.json](source-permissions.json)：只读官方公开接口文档；没有读取真实 Token、查询账户积分、请求市场接口、购买权限或添加事件 feed。现有 daily/calendar 授权不被推定为公司行为完整覆盖。

真实新增前向日、真实研究调用、Candidate、Paper/Live 订单/成交均为 **0**。完整真实行情、PDF、数据库、原始日志和本机路径只留 ignored 本地。

## 合成完整路径与反证

[readiness-tests.txt](readiness-tests.txt) 为最终完整 **13/13 PASS，exit 0**，[checks.json](checks.json) 保存原 SQLite/收据产生的结构化事实。最终整套包含无效 PR38 引用保持 UNKNOWN，以及同日完整覆盖和相同事实刷新后旧任务失效的反证；[quality-final.json](quality-final.json) 另外保留该来源状态的定向结果。

| 用例 | 实际结果 |
| --- | --- |
| 两套独立 23 日 schema-1041 journal / 当天 PR33 / 当天覆盖记录 | 各 21 日资格 ALLOW_RESEARCH_ONLY，明确 synthetic_test、真实日新增 0；各 1 个原 Agent task、1 次原 Fusion fake settled、1 个 Registry/Inbox 条目；重复 once 不增加调用 |
| 不足 21 日、交易日缺口、漏 feed/覆盖、空列表无覆盖契约、未来声明 | BLOCKED，0 原任务/调用/登记 |
| 事后取得、晚到覆盖 | 不能补写先前日；新失败 receipt 与旧 receipt 分开，旧失败内容可重验 |
| 事件部分事实、日期冲突、币种/金额/单位错误 | 部分事实和价格不可比阻断；不调整真实价格、不核算账户现金 |
| 编辑 ready/receipt、重算伪造 receipt SHA、坏 blob SHA、模式混用 | 严格 schema、原内容回放及 journal 模式绑定拒绝；Owner 未启用时 0 调用 |
| queued 后改事件证据、原 journal 未 sync 修订、Owner disable | **直接调用 Rust**，绕过 Python runner 重查，实际任务仍 cancelled，0 call/0 登记 |
| journal 修订/来源更正与旧 receipt | 当前资格阻断；旧冻结证据可回放，更正不抹掉旧失败或旧资格 |
| stale、future as-of、未来标签、复权语义、时钟回退、恶意路径 | BLOCKED；无效 PR38 不显示为来源已验证 |
| 发布前、commit 前、commit 后实际 `os._exit(86)` | 旧成功/失败证据不覆盖；本 store writer 正常恢复；重复发布复用同一 SHA；双进程竞争不双写 |
| A 失效、B 正常，B settled 后 kill/restart | B 精确执行和登记；A 未被 B 背书；B 不重复调用或计费 |
| 旧缺口/旧修订后形成新的干净 21 会话窗口 | 新窗口可审计和运行；原 journal/PR33 byte+mtime 不变，旧问题仍可见 |
| 同日补齐完整证据、仅供应商时间戳刷新 | 新收据可合格，原失败保持，旧 queued 任务 cancelled/0 call；实际事件更正仍阻断 |
| 原 reserve COMMIT 时撤销 Owner enable | 真实执行第二道 dispatch gate，原 call 为 **no_charge**、任务 cancelled；0 dispatched call/登记，重新 enable 也不重发 |

合成测试注入的是测试程序的时钟、fixture 和实际进程退出；生产 CLI 无时钟/force/历史取得时间参数。权限始终 `RESEARCH_ONLY / ELIGIBILITY_DENIED`，开盘/历史 PIT 不解锁。

## 必要回归与命令

全部精确参数、退出码、耗时、生产源码 SHA 及首轮失败保存在 [validation.json](validation.json)，原测试结果节选见 [regression-results.txt](regression-results.txt)。**123 个原 Python 唯一用例**通过，其中原沙箱失败项按下表原样在正常本机权限复跑；未修改旧测试定义、样本、协议或历史证据。

| 检查 | 结果 |
| --- | --- |
| `with-msvc.ps1 fmt --all -- --check` | exit 0 |
| `with-msvc.ps1 check --workspace --all-targets --locked --offline` | exit 0 |
| `with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings` | exit 0 |
| `with-msvc.ps1 test --workspace --locked --offline` | exit 0；162 tests |
| `with-msvc.ps1 build --workspace --locked --offline` | exit 0 |
| `python -X utf8 -B scripts/test-data-snapshot.py` | 11/11 |
| `python -X utf8 -B scripts/test-corporate-action-evidence.py` | 15/15；原 junction 用例需正常本机权限 |
| `python -X utf8 -B scripts/test-cash-dividend.py --exe target/debug/stratide-cli.exe --out <NEW_IGNORED_OUTPUT>` | 9/9；原隔离 synthetic 会计回归，无真实/前向账户动作 |
| `python -X utf8 -B scripts/test-forward-shadow.py` | 9/9 |
| `python -X utf8 -B scripts/test-multimodal-research.py --evidence <NEW_IGNORED_OUTPUT>` | 10/10 |
| `python -X utf8 -B scripts/test-multimodal-routing.py --evidence <NEW_IGNORED_OUTPUT>` | 4/4；隔离 authority，原 TST 默认 cap 不变 |
| `python -X utf8 -B scripts/test-eod-agent.py` | 6/6；原 junction 失败项单独复跑通过 |
| `python -X utf8 -B scripts/test-candidates.py` | 13/13 |
| `python -X utf8 -B scripts/test-eod-auto.py` | 16/16；15 项首轮通过，junction 项单独复跑通过 |
| `python -X utf8 -B scripts/test-research-review.py` | 12/12；11 项首轮通过，原 junction 项独立加载原定义后单独复跑通过 |
| `python -X utf8 -B scripts/test-eod-operator.py` | 18/18；16 项首轮通过，junction/Windows Credential Manager **合成专用条目**两项单独复跑通过并删除该假条目 |

Rust 临时文件使用新 ignored TEMP/TMP；没有修改生产预算/费用算术或提高 cap。新 Rust 改动仅为原实际任务读取同一 receipt，以及 checkpointed PR33 的无写读取。

## 保留的失败与修复

[red.txt](red.txt) 保留开发失败节选，没有把首轮失败替换成全绿。

1. 首次正向闭环可归档，但原 snapshot 空 SHM 的 mtime 改变。原 Rust reader 改为 checkpointed 文件 immutable + 文件头/前后 SHA 核验；首轮 immutable 又暴露 SQLite 将 `journal_mode` 报为 delete，随后改为核对 WAL 文件头。最终两套 E2E 的原文件 byte+mtime 均一致。
2. 新 init 成功但显示 BLOCKED 时的退出码、Windows UTF-8 JSON 和测试真实路径规范化在初次真实 audit 时修正；没有写原数据。最终真实 audit/query 都按约定拒绝并可重复核验。
3. dispatch 反例第一轮误把原 CLI 的 `FUSION_FAILED` 退出码当成 0；改为按原契约断言 exit 2。原 no_charge/取消行为没有改写。
4. 原 PR52 10 项先通过，接续路由测试时共享合成 Agent 当日 TST 已耗尽，按原规则 `DAILY_BUDGET_EXHAUSTED`。使用新的隔离 Git authority 后 4/4 通过；原 cap、既有费用和未知状态不重置。
5. 原 junction/合成 Credential Manager 用例在文件沙箱内遭系统拒绝；只对失败项使用正常本机权限复跑，均通过。这不是自动审批拒绝，也不是删测试或放宽路径拒绝逻辑。

隔离 authority 的可复现 Windows 设置（仅测试进程；不迁移/重置原 Agent）：

```powershell
$stratideCheckout = (Get-Location).Path
$stratideValidation = Join-Path $stratideCheckout ('state/pr11-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stratideValidation | Out-Null
git -C $stratideValidation init --quiet
$stratidePreviousGitDir = $env:GIT_DIR
$stratidePreviousWorkTree = $env:GIT_WORK_TREE
try {
  $env:GIT_DIR = Join-Path $stratideValidation '.git'
  $env:GIT_WORK_TREE = $stratideCheckout
  python -X utf8 -B scripts/test-forward-readiness.py --evidence state/pr11-test-results
} finally {
  $env:GIT_DIR = $stratidePreviousGitDir
  $env:GIT_WORK_TREE = $stratidePreviousWorkTree
}
```

## 未验证项

真实连续 21 日与独立事件 feed 的完整性/历史版本/按时取得尚无证据；当前无法真实解锁。离线契约和哈希不自动认证事实。账户税务/到账、历史 PIT、可信开盘、真实 Provider/外部模型、真实研究效果/alpha、前向 Paper/Live 成交/NAV、物理断电、其他 OS、长期常驻稳定性均未验证。无常驻服务、UI、财务迁移或交易权限变更。保持 Draft，等待固定 HEAD 审查及 Owner 决定。
