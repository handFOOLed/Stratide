# PR52 / PR54 原完整回归：盘后实际证据

响应 [最新审查](https://github.com/handFOOLed/Stratide/pull/56#issuecomment-6568334369)中剩余的 P1 证据要求。实际运行 HEAD `4ad0a3d716ee8acc3f43e58db463714cf51a2bbc`，分支 `codex/issue55-cloud-risk-portfolio`。本次交付只追加文档与证据，生产代码和原测试字节未改；交付固定 HEAD 在唯一 Draft PR #56 描述中核对。

三个进程在 **2026-11-02 17:10:56 UTC+8 / 09:10:56 UTC** 启动。原 snapshot 夹具的当日 17:00 来源时间已实际生效。使用三个各自独立的 synthetic Git authority，TEMP/TMP 指向 ignored 工作区；不修改系统时钟、原 fixture 或安全时钟门禁。

| 原完整套件 | 实际项目数 | failures / errors | exit | 耗时 | 日志 / 原结构化结果 |
| --- | --- | --- | --- | --- | --- |
| `scripts/test-multimodal-research.py` | **10/10 PASS** | 0 / 0 | **0** | 72.97 秒 | [日志](multimodal.txt) / [checks](multimodal/checks.json) |
| `scripts/test-multimodal-routing.py` | **4/4 PASS** | 0 / 0 | **0** | 38.50 秒 | [日志](routing.txt) / [routing](routing/routing.json) |
| `scripts/test-forward-readiness.py` | **13/13 PASS** | 0 / 0 | **0** | 192.55 秒 | [日志](readiness.txt) / [checks](readiness/checks.json) |

实际命令、UTC/本地时间、时区、耗时和退出码见 [execution.json](execution.json)。以下 `<out>` 为本目录相应子目录；各套件的 Git authority 分别隔离，不共享测试数据库。这里的新目录仅为原 fake-only 回归所需的 synthetic 隔离，不是替换或重置 Owner 费用权威。

```text
python -X utf8 -B scripts/test-multimodal-research.py --evidence <out>/multimodal
python -X utf8 -B scripts/test-multimodal-routing.py --evidence <out>/routing
python -X utf8 -B scripts/test-forward-readiness.py --evidence <out>/readiness
```

[source.json](source.json) 绑定 24 个实际源码 SHA 和运行 HEAD。三套原脚本与 snapshot 夹具对照原首轮 HEAD `a24c8feba1811d474db19db28628b95898963191` 的字节未变；测试前后再次核对全部 24 个 SHA 与运行 HEAD 的 Git blob 一致。[test-build.json](test-build.json) / [test-build.txt](test-build.txt) 是上午为同一 HEAD 准备当前 test executable 的实际编译记录，包含 5 个所需二进制 SHA。其 `tests_executed=0` 只描述 `--no-run` 编译，不作为本次 27 项的 PASS 来源。

[preservation.json](preservation.json) 证明原 observer、PR33、PR38、PR54 和旧 Agent 共 **20 文件**的 byte SHA、长度和 mtime 在回归前后均与最初基线一致。原上午无效时间失败仍保留在上级历史证据目录；本次三套首轮均 exit 0，无需代码修复或权限复跑。原 Review 的 12 项首轮 exit 1 与 junction 单项 exit 0 在 R1 中分别保留，不能合并声称首轮整套 exit 0。

本轮只有 synthetic/fake 输入和 TST 费用，0 真实云/付费/行情请求，0 真实订单或交易授权。全部为开发者测试，最终独立复审仍 **NOT_VERIFIED**。真实云身份/计费/模型效果、真实市场资格与 Paper/Live 仍不由这些回归证明。保持 Draft，不 Ready、不合并。
