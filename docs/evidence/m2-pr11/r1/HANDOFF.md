# PR56 原始回归盘后续跑

本次修复仍未完整关闭审查。预算权威的实现和当前 177 Rust / 13 新 E2E 已通过；另一个 P1 必须在有效真实时间补齐原三套回归。应用已建立本聊天单次 heartbeat `pr56`，计划 **2026-11-02 17:10 Asia/Singapore（同 Asia/Shanghai，UTC+8）**，RRULE `FREQ=DAILY;BYHOUR=17;BYMINUTE=10;BYSECOND=0;COUNT=1`。不得重复建立调度。17:00 来自原 snapshot 夹具，不修改原数据时间以提前通过。

1. 使用当前 `issue55-worktree` 与 `codex/issue55-cloud-risk-portfolio`，读取 PR #56 当前固定 HEAD。核对仍为 open Draft、没有外部源码改动，并将本目录 `tested-source.json` 的 17 个 SHA 与当前 Git blob/工作区核对。只继续这一个 PR；不要 Ready/合并。
2. 读取真实 UTC 和 UTC+8 日期；必须当日 17:10 后。保持三个原脚本及原 `test-data-snapshot.py` 与 `a24c8feba1811d474db19db28628b95898963191` 字节一致。不改系统时钟，不 mock 生产或原测试的时钟门禁。
3. 在 ignored `state/issue55-r1-afternoon/` 下分别创建三个 Git authority（每个 `git init`），为各自子进程设置 `GIT_DIR=<authority>/.git`、`GIT_WORK_TREE=<当前 checkout>`，移除继承的 `GIT_COMMON_DIR`。TEMP/TMP 均用 ignored `state/issue55-r1-temp`。原 fake-only 套件在各自 synthetic authority 下运行；不得打开/重置 Owner 的真实 Agent 或改原真实来源。
4. 使用当前已构建的 binary，以 Python `-X utf8 -B` 运行以下**全套**原测试。每套记录真实命令、开始 UTC/本地时间与时区、退出码、耗时、当前固定 HEAD 及源码 SHA。公开证据放 `docs/evidence/m2-pr11/r1/afternoon/`；日志脱敏，保留所有初始失败。

```text
python -X utf8 -B scripts/test-multimodal-research.py --evidence <out>/multimodal
python -X utf8 -B scripts/test-multimodal-routing.py --evidence <out>/routing
python -X utf8 -B scripts/test-forward-readiness.py --evidence <out>/readiness
```

5. 预期为 10、4、13 项，不能把 setUpClass 0 项或有失败的 exit 1 计为 PASS。若发现本期真实回归，修复最小相关问题，保留原失败，并按改动重新验证；不要为通过测试抬预算、清空历史或修改原定义。若仅 Windows junction 权限失败，可在正常 Windows 权限下重跑原失败项，清楚记录完整 suite 与唯一项结果。
6. 用 ignored `state/issue55-validation/protected-before.json` 的原清单重新核对 20 个原 observer/PR33/PR38/PR54/旧 Agent 文件的 byte SHA、长度及 mtime，输出不含私有路径的保全清单。不要读取/输出 Owner token。
7. 更新 R1 README、STATUS、路线图、双语 README 与现有 PR body 的状态，追加当前测试证据。提交并推送同一分支；验证新固定 HEAD、全部测试源码与提交字节一致、PR 仍 Draft/open/unmerged。开发者测试不等于独立复审 PASS。真实 Provider、费用/模型能力和交易均保持 NOT_VERIFIED/BLOCKED。
8. 完成后仅通知有意义结果并关闭本次调度；若 app 已因 COUNT=1 消耗调度则不建立新的。禁止 paid API、行情采集、Tushare 外发、交易权限、子 Agent、新 PR、Ready 或 merge。
