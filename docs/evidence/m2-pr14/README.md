# M2-PR14 开发证据（2026-11-03）

执行 [Issue #61](https://github.com/handFOOLed/Stratide/issues/61)，base `525f0633a7b9a62c96b1a1ab48b3f917b9b2df9f`，分支 `codex/issue61-multistock-research`。最终 HEAD 在唯一 Draft PR 正文中给出；本目录是开发者执行证据，未取得独立验收。

真实全区间运行完成，但三个固定研究规则未建立相对等权基准的可信优势。动量/反转严重亏损；逆波动基础成本结果低于等权，压力成本转负。保留全部结果，没有据此重新选参数或筛掉失败规则。收益都是带缺口及未认证执行假设的调整价格近似指数。

## 实际范围与资源

- 2021-11-01—2026-10-30，共 1212 个源会话；版本上界 V1=1212、V2=4848。
- 读取 6,347,781 条日线、19,221,401 条 sidecar 标准化行，合计 25,569,182 行。读取的是已准入规范行，不是旧 raw HTTP 全量重验。
- 实测 5774 个代码，累计 5387 个代码曾满足沪深研究子集条件；源行含 196 个今日目录标 D 的证券，未按今日存活列表删去历史。BSE 277,129 行单列，不进入已确认日历子集。
- 同期有 378 个行情连接缺因子、11,293 个缺每日指标、223 个基本指标 close 冲突、11,441 个缺限价；4,158 次观测序列在缺口后重新出现。它们不被补 0，也不能据缺日认定停牌。
- 因子旧 1212 日 PARTIAL、日线 11 日 PARTIAL、限价 33 日 PARTIAL 原准入记录保留；未虚构 adj_factor 数字 cap 或把下载完成说成全市场/PIT 获证。
- 真实数据实际取得 UTC 区间：`2026-11-02T05:28:40.872982+00:00`—`2026-11-02T14:23:42.415409+00:00`。
- 真实本轮运行：新加坡时间 2026-11-03 09:10:37—09:19:38；耗时 540.980 秒、CPU 316.125 秒、峰值 267.547 MiB，1 worker / 1 thread。Windows / Python 3.12.10 / SQLite 3.49.1。新实验产物约 20.17 MB，原库复制 0。
- 先执行 3 股票 × 80 会话 / 240 行真实 smoke，再执行一次全范围研究 pass；没有用 3 股票替代真实大范围运行。
- Tushare 数据 API、Token 读取、云模型、付费均为 0；未启用 GitHub CI。

## 全期成本敏感性

从无量纲 1 起步，含暖启动空暴露；gross/base/stress 具体比例与限制见 [契约](../../M2_PR14.md)。表内是累计假设收益，非账户或认证含税总回报。

| 规则/基准 | gross | base | stress | base 最大回撤 | base Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20/60 动量 | -98.21% | -98.72% | -99.18% | -98.72% | -2.060 |
| 5 日反转 | -59.86% | -77.30% | -88.45% | -78.27% | -0.978 |
| 20 日逆波动 | 44.82% | 8.64% | -26.32% | -19.38% | 0.198 |
| 现金 | 0.00% | 0.00% | 0.00% | 0.00% | N/A |
| 全合格子集等权 | 30.78% | 27.49% | 23.21% | -33.64% | 0.331 |
| SMA20/60 | -33.66% | -43.71% | -54.89% | -46.78% | -0.440 |

| 规则/基准 | base 累计双边换手 | base 拒绝变更次数 | stale 会话数 | 最高 stale 权重 |
| --- | ---: | ---: | ---: | ---: |
| 20/60 动量 | 200.457 | 398 | 194 | 9.79% |
| 5 日反转 | 376.538 | 3951 | 958 | 48.80% |
| 20 日逆波动 | 175.726 | 159 | 339 | 9.38% |
| 现金 | 0.000 | 0 | 0 | 0.00% |
| 全合格子集等权 | 15.479 | 27992 | 1148 | 1.61% |
| SMA20/60 | 100.060 | 189 | 145 | 4.10% |

stale 数量尤其影响反转与等权结果：缺价持仓按上次观察值明确 carry，不能把该路径解释成已证明能出售的资产价值。每个情景的期末零回收敏感性、成本、年化、波动及拒绝原因都在 [真实汇总](real-summary.json)。所有变更均为分数研究暴露，未建模 100 股整手/最低佣金，没有生成实际订单、成交或账户 NAV。

## Walk-forward（每窗重置，base 情景）

开发段为 2021—2022，验证段为 2023。三个后期窗口的参数在计算前固定，没有训练拟合、全期选优或赢家筛选。各窗口沿用左侧已完成特征，首个源会话 embargo，horizon/purge 均为 1；不是独立 PIT 盲测。

| 规则/基准 | 2024：241 会话 | 2025：242 会话 | 2026：197 会话 |
| --- | ---: | ---: | ---: |
| 20/60 动量 | -76.57% | -30.51% | -45.99% |
| 5 日反转 | -17.27% | 1.28% | -61.48% |
| 20 日逆波动 | 30.17% | 3.92% | -9.10% |
| 现金 | 0.00% | 0.00% | 0.00% |
| 全合格子集等权 | 4.14% | 39.94% | -14.69% |
| SMA20/60 | -2.17% | 15.17% | -39.82% |

实际评测段分别为 2024-01-03—12-31、2025-01-03—12-31、2026-01-06—10-30；首源日分别 2024-01-02、2025-01-02、2026-01-05，被明确排除。全期连续路径的开发/验证/后期分段，以及三个独立重置窗口的全部 gross/base/stress 指标均保留在 JSON。

## 冻结与复核

- Plan SHA：`c542061a63b2b8cfb363e5825aab96abb130cefeb17817167bd56376fc5b2838`。
- Source SHA：`f8eafe09ebce5538775faa7539ceb466f2284205f32f689f95c0d95570f58a96`。
- Query SHA：`09c5bb6761e762c03a8ad58c1c193917427c5a876c928b8cd50411b2453c9bcf`。
- Output SHA：`13d13ab8361639e1ab2396e89efb65b8e36e9116f1d2fac0146d4fe48da34f15`。
- 完整 `plan.json` / source refs、源代码快照、daily/signals 和报告留在本机 ignored `state/multistock-research/issue61-real-20261103/`。Git 中只保存脱敏统计/散列，不携带原行情、库、完整研究序列或绝对路径。
- [冻结配置/代码散列](frozen-plan-summary.json)、[实际资源/前后收据](execution.json)、[新产物验证](verification.json)、[执行/测试边界](validation.json)。同配置/源输入的两次 synthetic E2E 输出 SHA 相同；冻结上界下的数据修订不改旧视图。
- 实际 CLI `plan` 重新读取小型版本元数据后得到相同 Plan SHA；`report/verify` 只读新实验文件，exit 0。未为复现再扫描一遍五年真实行。

## 定向测试与红绿反证

`python -I -B scripts/test-multistock-research.py`：**12/12，exit 0**；[完整日志](tests-green.txt)。90 个 synthetic 会话、8 个代码，包含新上市/期间退市、缺日、NULL 因子、S 事件、限价、exchange 冲突、不可靠身份、后续因子事件和费用。测试还覆盖原 writer/WAL/schema 边界、禁止源内输出、冻结修订、输出篡改、现金/复权守恒及 CLI 只读。

[红色反证](future-volume-red.txt)在内存中故意让开盘门使用次日全天 vol；同一生产检查的前向泄漏反例出现 1 个预期失败。撤销该内存替换后，12 项全部绿色，生产源文件没有被此实验修改。初始无实现时还实际得到 `ModuleNotFoundError`；有效金融反证以此 future-volume 失败为准。

## 源库未写与命令

原 PR58/60 绑定与哈希验收直接复用。读取依赖原只读锁、schema 校验和 immutable/query_only；只比较两个源根各自已知 SQLite/锁/WAL/SHM/journal 的尺寸/mtime，前后完全一致（见 execution）。没有源库复制、旧 raw 扫描、旧全状态 SHA/mtime 遍历、旧 verify 或源库索引改动。Rust/Agent/旧采集代码未变，因此没有重复运行其全量测试；Linux/macOS 未执行。

```powershell
python -I -B scripts/test-multistock-research.py
python -I -B scripts/multistock-research.py inspect --v1-root <V1_ROOT> --v2-root <V2_ROOT>
python -I -B scripts/multistock-research.py plan --v1-root <V1_ROOT> --v2-root <V2_ROOT> --v1-version 1212 --v2-version 4848
python -I -B scripts/multistock-research.py run --v1-root <V1_ROOT> --v2-root <V2_ROOT> --v1-version 1212 --v2-version 4848 --out state/multistock-research/issue61-real-20261103
python -I -B scripts/multistock-research.py report --out state/multistock-research/issue61-real-20261103
python -I -B scripts/multistock-research.py verify --out state/multistock-research/issue61-real-20261103
```

上述实际运行/只读命令均 exit 0；已存在实验目录拒绝覆盖，重跑需使用新的输出目录。V1/V2 locator 从 Owner 现存本机目录显式提供，新研究输出另行指定；不隐式访问 forward/Agent/Risk/Ledger。

最终保持 `historical_backfill_ex_post / NOT_VERIFIED / BLOCKED / ELIGIBILITY_DENIED / paper_allowed=false / live_allowed=false`。唯一 Draft，等待固定 HEAD 审查和 Owner 决定；没有自行 Ready 或合并。
