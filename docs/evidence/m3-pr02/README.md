# Issue #83 本地开发验证

基线 `cf86668b0360f7bf7343d1bbbfc80ad0d6b813e5`，执行约束 `change hash=allow agents=0`。本目录只有开发者验证，无独立审查或 Owner 生产出网授权。

## R1：研究故障与 EOD watch 隔离

R1 基于 `31821172812809c4c0d53ff33978ed3c21aed1e7` 修复调用边界。新增 5 项回归在旧实现复现 4 项异常退出；修复后 [完整市场源回归 23/23 通过](r1-market-eod-tests.txt)，前端 `typecheck` 通过。定向场景包括：持久配置原为 OFF 但 Agent SQLite 不可读；启用研究后写库失败；Worker 异常；单次 `once` 保留已成功 EOD 结果；`KeyboardInterrupt/SystemExit` 仍退出。watch 场景实际经过合成 HTTP 采集与原 journal，核对两日 READY 快照和两次 daily 请求均保留；研究报 `BLOCKED/RESEARCH_UNAVAILABLE`，故障原文不外露，Provider 调用为 0。

这次只改可选调用边界、相关回归和 P2 的暖机/时点说明，不改研究任务、预算、授权或未知结果重发规则。原下表验证是首版结果，R1 未重复执行 Rust、真实模型或云 E2E；旧证明文件保留。Agent DB 故障时的状态来自本轮 CLI JSON，不声称已经写入不可用的 DB；同步研究仍有原超时限制，不保证故障期间每隔精确 30 秒开始采集。

| 检查 | 结果与边界 |
| --- | --- |
| 新研究链路 | [8 项通过](market-research-tests.txt)：记录式全市场源 → 8 证券 CPU 测试传输 → libtest loopback → 原 Registry；拒绝授权缺字段/错用途/撤销/过期、未知结果、共享预算耗尽、未来时点/缺样本、并发、部分 CPU 失败、派发后强杀恢复。非真实云调用。 |
| 原数据源 | `python -B scripts/test-market-eod.py`：18 项通过，合成 HTTP；无真实 Tushare 请求。 |
| 原 Provider / 预算 | `cargo test --locked -p stratide-research --lib --test cny_budget`：30 项库测试 + 3 项 CNY 预算测试通过。 |
| 原 synthetic Fusion | 原 `test-local-timesfm-fusion.py` 的完整任务/归档/只读核验和授权撤销/关闭两项通过；使用同一隔离 CNY fixture 与 libtest loopback，无真实 key。 |
| 前端 | `typecheck`、`build` 和 `tests/market-research.config.js` 的单个浏览器用例通过：不预选许可、独立开关、字段范围确认、只读预览与刷新、撤销、1280/375 无横向溢出。截图位于 ignored `state/issue83-ui/`，已查看实际像素。 |
| 真实本地模型 | [local-real-cpu.json](local-real-cpu.json)：已有授权历史输入 3 证券 × 84 会话；原权重、当前 Worker、WSL2 cgroup/bubblewrap，约 3.28 秒，零新增 Agent 任务、行情请求、云调用。只证明本地历史重放，不是新全市场 READY 或预测收益验收。 |
| 真实市场云 E2E | `NOT_AUTHORIZED_NOT_RUN`；未替 Owner 保存生产许可，未读取真实 key/Token 正文。 |

定向 Python 测试必须在独立、一次性 Git 仓库编译并运行，不能指向 Owner 状态。`MARKET_TEST_DRIVER` 指向该仓库编译的 libtest 可执行文件，建议复制为稳定测试路径，避免其他 Cargo 构建覆盖驱动。`MARKET_TEST_REUSE_FIXTURE=1` 仅用于明确命名的 `issue83-acceptance` 合成测试仓库，可复用已构建的 92 会话收据；该选项会清理这份测试库的任务/调用，不能用于真实实例。首轮源构建约 2 分钟，后续相关 8 项约 1 分钟。

Windows 测试环境的系统临时目录存在写入限制。Rust 和 Edge 的检查使用工作区内 `TEMP/TMP`，在正常本机权限下执行；未通过修改生产逻辑绕开检查。最初红测检出了空停牌事件表表示、旧历史查询截止范围、跨语言 canonical SHA 和测试管道/旧 marker 问题；最终相关检查均通过。

保留所有旧 Registry、任务、calls、预留和证明文件；本次未操作 Owner 真实数据库。模型冒烟另在新临时工程复用 venv 和硬链接权重，只读原冻结输入，不重签或覆写原历史任务。测试中 key 均为明确 dummy，loopback 只存在于 libtest，生产二进制没有该覆盖入口。

不包含原始行情、持仓、账户余额、密钥、凭据定位文件或 Provider 原始响应。候选仍为 `RESEARCH_ONLY / ELIGIBILITY_DENIED / paper_allowed=false / live_allowed=false`。不声称 PIT、N100、全市场接口权限、真实前向收益或独立验收通过。
