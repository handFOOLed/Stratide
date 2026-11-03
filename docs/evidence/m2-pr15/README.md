# Issue #63 开发者证据

本证据对应独立分支 `codex/issue63-autonomous-research`，base `cb624bc6308add4ee9d1f04b35cbac591f0cd7e8`。固定提交 HEAD 见唯一 Draft PR。全部为开发者自测和真实本机历史研究记录，**不构成独立验收、PIT 认证、Alpha 或 Paper/Live 资格**。

## 交付与实际执行

完整 CLI、受限 AST/提案器、同源多候选评价和恢复控制见 [M2_PR15](../../M2_PR15.md)。真实实验一次授权后实际运行 **2 轮 / 8 个不同合法 AST / 0 提案拒绝**，每轮四个候选、现金、受 50 个实际持仓上限约束的确定性等权和简单正收益基准，均报告 gross/base/stress 与分窗/重置 Walk-forward。最终状态 `COMPLETED`、累计 trial=8，达到两轮上限后不再启动。

第二轮提案真实消费首轮的**开发段投影**：四个候选在开发段均为非正收益，预定回撤规则触发 `reduce_exposure=true`，下一轮四个新 AST 敞口均为 0.5。没有使用验证/曝光评价段调参、挑赢家或增加交易权限。试验级 plan SHA、轮次 SHA 和内容哈希防止同一已完成轮次重复执行；同一 Owner 授权实验内累计所有尝试和候选，不把新轮次称为新盲测。

原 V1=1212 / V2=4848，范围 **2021-11-01—2026-10-30**，每轮 **1212 会话、6,347,781 日线 + 19,221,401 sidecar = 25,569,182 标准化行**；实测 **5774 个代码，5387 个代码曾进入研究子集**。每轮只进行一次按日历史读取，多候选共享该次输入。第二轮是开发段反馈后新提案的实际研究，不是再次复核旧 raw/旧库哈希；两轮使用相同的 1212 个历史会话，不增加前向天数。

| 项目 | 第 1 轮 | 第 2 轮 |
| --- | ---: | ---: |
| 评价耗时 | 278.750 秒 | 278.672 秒 |
| CPU 时间 | 278.094 秒 | 277.938 秒 |
| 评价阶段实测峰值 | 437.793 MiB | 438.727 MiB |
| 新轮次档案 | 66.988 MiB | 66.615 MiB |
| workers / threads | 1 / 1 | 1 / 1 |
| 原库复制 / 新行情 API / Token 读取 | 0 / 0 / 0 | 0 / 0 / 0 |
| 云模型 / 付费调用 | 0 / 0 | 0 / 0 |
| 已知源文件收据前后相同 | true | true |

Windows、Python 3.12.10、SQLite 3.49.1。默认每次 1800 秒、512 MiB、整个新实验 256 MiB，每 100 会话 checkpoint；两轮均未触发资源停止。计时和峰值取自评价阶段收据，包含实际读源、策略执行与 checkpoint，不把产物 verify 算成旧源扫描。完整日账、行 SHA、目标权重、极端日价格贡献、持仓 checkpoint、本机 locator 和源收据均留 ignored `state/autonomous-research/issue63-real-20261103/`。

## 结果如实保留

下表是无量纲调整价格暴露指数的**全期 base 假设收益**；没有人民币本金、真实股份/成交或账户 NAV，未认证整手、最低佣金、实际流动性、税或分红到账。第二轮风控敞口变化已预先由开发段规则决定，两个数不能当作模型样本外改善证明。

| 规则/基准 | 第 1 轮 | 第 2 轮 |
| --- | ---: | ---: |
| 正向收益候选 | -99.5745% | -89.7527% |
| 逆向收益候选 | -78.7467% | -42.6702% |
| 低波动/流动性交集 | +7.9166% | +5.1177% |
| 跨特征 rank 加权/OR 筛选 | -14.5033% | +1.2011% |
| 现金 | 0.0000% | 0.0000% |
| 同上限确定性等权 | +1.6064% | +1.6064% |
| 简单正收益筛选 | -55.0657% | -55.0657% |

失败没有删除或因收益负值被标为工程失败。第一轮正向候选存在 -99.57% 最大回撤；逆向候选有 971 个 stale 会话，最高 stale 权重约 49.66%。这些暴露与拒绝原因、最差日及「stale 暴露零回收」敏感性保留在报告；不能把陈旧估值当成可清算资产。正收益候选同样没有获得晋级或 PIT 资格。

固定 `EXPLORATORY_EX_POST / REUSED_EXPOSED_PERIOD`。2024–2026 已在 PR62 曝光；新 seed/AST/轮次不恢复盲测独立性。多重比较、选择偏差和真实前向证据缺失限制持续有效。

## 测试与反证

- [新增定向测试](tests-autonomous.txt)：**12/12，exit 0**。四种结构/seed/去重、非法类型/单位/未来 lag/复杂度、旧文本与伪造来源、两轮 E2E/不可覆盖、开发段投影和 hidden holdout 拒绝、时点/成本/基准/实际持仓上限、独立 Decimal 小账、freeze/evaluate/publish/archive/已封存后状态恢复、失败保全/篡改、暂停取消/资源/并发、NULL 估值、空提案和只读零副作用。
- [PR62 定向回归](tests-pr62-regression.txt)：**12/12，exit 0**。保留复权/现金/费用、下一开盘时点、未来成交量反例、只读/WAL/schema/修订/复现等原基线。没有重算其真实 25m 行或修改旧报告。
- [费用符号红色反证](cost-sign-red.txt)：可信测试进程内暂时将原 `cost_rate` 符号反转，独立几日 Decimal 账立即出现 **1 个预期失败，exit 1**；撤去进程内 mutation 后完整定向测试 exit 0。预期账用字面 buy/sell/滑点/费率和 cash/units/index 逐步独立计算，没有调用实现的价格/成本/统计函数计算期待值；同时对照四本同源候选账。测试涉及亏损，亏损本身不触发失败。
- [新增档案核验](verification.json)：两轮均 `SEALED`，日账重建指标和源/代码/AST/产物/尝试审计哈希通过；原源码 SHA 与冻结代码完全一致（见 `real-summary.json` 的 `frozen_code_matches_current=true`）。仅核验新档案，不是独立评价员认证。

Linux/macOS、真实 Provider、真实前向观察、PIT/历史身份/完整历史 Universe、真实可成交性未验证。Rust Agent/预算/Risk/账本、Operator/Observer 和 Dashboard 均未修改，未运行无关 Rust 全套测试；没有新增模型或云服务。

## SHA 与可复现命令

- Plan SHA：`41e5b2cde6792fdf8ab9787283584067f910b273450b6ae1b63734745c3e1c80`
- Source SHA：`f8eafe09ebce5538775faa7539ceb466f2284205f32f689f95c0d95570f58a96`
- 第 1 轮 output SHA：`e0aa0b2f2237172382df153238f647ecc3e08c1af7b043b9fbb880f1de0e6d1e`
- 第 2 轮 output SHA：`a1c55cb421cf0bc379506c808ec4106aa994bb41d0ad44d17fb71f5feeffe3bf`

[冻结计划摘要](frozen-plan-summary.json)保留配置、代码 SHA、版本上界和资源；[真实聚合结果](real-summary.json)保留每轮三成本、base 分窗/重置 Walk-forward、失败、拒绝、stale 和反馈；[命令及 exit](commands.json)记录实际执行。真实路径已替换为 locator，Git 不保存任何行级行情、原库、Token 或原本机绝对路径。

```powershell
python -I -B scripts/autonomous-research.py plan --v1-root '<V1_ROOT>' --v2-root '<V2_ROOT>' --v1-version 1212 --v2-version 4848 --seed 63
python -I -B scripts/autonomous-research.py init --v1-root '<V1_ROOT>' --v2-root '<V2_ROOT>' --v1-version 1212 --v2-version 4848 --seed 63 --out state/autonomous-research/issue63-real-20261103 --authorize-local
python -I -B scripts/autonomous-research.py once --out state/autonomous-research/issue63-real-20261103
python -I -B scripts/autonomous-research.py once --out state/autonomous-research/issue63-real-20261103
python -I -B scripts/autonomous-research.py report --out state/autonomous-research/issue63-real-20261103
python -I -B scripts/autonomous-research.py verify --out state/autonomous-research/issue63-real-20261103
```

上述实际执行均 exit 0。再次对已完成实验 `once` 只返回既有报告；复现实验的独立副本须使用新输出目录，相同 seed/数据/规则产生相同提案和经济结果。已有失败文件和封存报告不可覆盖。
