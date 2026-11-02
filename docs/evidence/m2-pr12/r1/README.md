# PR #58 R1：两项 P1 定向修复

对应 [ChatGPT 审查](https://github.com/handFOOLed/Stratide/pull/58#issuecomment-6572018595)，被审查 HEAD 为 `185f53ed833f3762c01cee6d58f43c625b14c803`。本轮在原独立分支更新同一个 Draft PR，`agents=0`；未经 Owner 批准不 Ready、不合并。这里是开发者反证和自测，不是 ChatGPT 独立复审通过。

## P1：不完整刷新不再降级当前完整视图

选择“低质量刷新只保存 attempt/raw”。发布层以 checkpoint 为当前版本：已有 COMPLETE 时，empty、NULL 字段、疑似截断，或低于上限但丢失既有证券的响应，不进入日版本序列，不改旧 manifest/checkpoint。新尝试记录 `PARTIAL_REFRESH_REJECTED_<原因>` 并重封其元数据 SHA，HTTP/供应商码、原响应 SHA、行数和 canonical SHA 保留。报告单列拒绝次数和原因；包含拒绝的 CLI 刷新返回 exit 2。

默认 query 读取 checkpoint；as-of 从曾准入版本中选择，拒绝尝试不构成版本。完整合法且包含原证券的修订仍能原子晋升，旧冻结输出不变。

- [先红](p1-red.txt)：COMPLETE A/B 经 empty、NULL、缺股、满 6,000 行后分区四种刷新，原查询 SHA 全部改变。
- [CLI 先红](cli-refresh-red.txt)：核心拒绝已生效时，CLI 仍曾返回 exit 0；现在传递拒绝为 exit 2。
- [最终绿](windows-all-green.txt)：四类反例保持旧 query SHA、checkpoint、COMPLETE 数和 as-of；新 raw/拒绝原因可查；随后正常修订能晋升。合成 `verify` 复核被拒绝响应的 raw/canonical/元数据绑定。

首次取得的 PARTIAL 数据仍按原契约发布；本修复不把未知字段补齐，也不升级市场/PIT/交易资格。

## P1：在连接/写入前拒绝内部链接

根路径保留词法形式，不先 resolve 掉链接。CLI、读写入口检查根及既有后代；连接主库/sidecar、打开锁、创建 raw/pending 和 rename 前也检查具体路径及父路径。采用原 journal 的 `is_symlink/is_junction` 风格，覆盖主库、锁、`-wal/-shm/-journal`、raw 文件/目录及 pending。

普通异类 SQLite 也在 WAL 设置之前校验 schema/契约，拒绝时不执行 checkpoint。没有新迁移、沙箱框架或旧金融核心变更。

- [Windows junction 红](windows-junction-red.txt)：在真实 NTFS junction 上，旧 preflight/backfill/resume 均未拒绝；可观察到连接/凭据读取，合成目标目录确有变化。
- [首次反证](p1-red.txt) 还保留异类普通 SQLite 被设置 WAL、bytes/mtime/SHA 改变的失败。
- 最终 Windows 实测文件 symlink 指向模拟旧 SQLite，另覆盖锁、三种 sidecar、raw 和 pending；三个 CLI 写命令均在 connect、凭据读取和网络前拒绝，模拟旧库 bytes/mtime/SHA 保持不变。真实 raw junction 同样通过。所有目标都在本 worktree 合成临时目录内，未对真实旧库做破坏性复现。

## 实际验证与权限记录

最终命令：

```powershell
python -I -B scripts/test-historical-warehouse.py
```

**Windows 最终同源运行：30/30 PASS，0 skipped，exit 0。** 包含原 24 项、刷新负例、真实文件 symlink / junction、异类 DB 不切 WAL 和 CLI 拒绝传播。执行前后生产/测试文件 SHA 一致，见 [tested-source.json](tested-source.json) 和 [validation.json](validation.json)。

保留权限及测试准备中的实际失败，不将跳过计为通过：

- 受限环境不能创建 junction；正常 Windows 用户环境可创建并实际完成反证。
- 普通用户缺 `SeCreateSymbolicLinkPrivilege`，文件 symlink 两项曾明确跳过；[当次记录](green-user.txt) 保留。
- 随后经 UAC 运行同样的两个合成文件用例，[两项实际通过](windows-file-links-green.txt)，没有跳过；最终又以相同方式对最终源码运行全部 30 项，[统一输出](windows-all-green.txt) 无跳过。只提升测试进程权限，没有更改 Windows 策略或开发者模式。
- 首次修复后普通用户回归还遇到 junction 创建权限及测试自身 SQLite 句柄未关闭的清理错误，[首次记录](green-normal-first.txt) 保留；清理改为显式关闭，业务断言未放宽。

## 真实数据兼容与保全

[checks.json](checks.json) 记录本轮只读复核：

- 真实三证券 20 日查询 60 行、2026-10-30 全市场扫描 5,571 行、as-of 1212 输出，与首轮输出逐字节一致，SHA 相同。
- 原真实仓库仍为 6,347,781 行，1,201 日 COMPLETE / 11 日 PARTIAL，native 总请求仍 1,235。本轮 **0 真实请求、0 购买**。
- 1,237 个真实仓库文件、4,544,217,419 bytes，与首轮完整 verify 后指纹相比 bytes/mtime/SHA 全部不变。
- 14,902 个原文件的 bytes/mtime/SHA 仍不变；没有改旧 Observer、Agent、Risk/Ledger、PR56 测试/时钟/等待脚本，也没运行其既定回归。

本轮未再次扫描 635 万行做完整真实 `verify`：数值解析和已存行没有改变，使用首轮固定 HEAD 的完整校验作为历史证据；当前源码新增的拒绝尝试验证由合成生产路径 `verify` 覆盖，真实数据则通过全文件指纹、只读查询及统计证明兼容。没有把旧全量校验冒称为新 HEAD 独立验收。

整体 `coverage=PARTIAL`、`historical_pit_status=NOT_VERIFIED`、`forward_research_readiness=BLOCKED`、`paper/live=false` 保持。

## Owner 数据策略

按 [Owner 后续决定](https://github.com/handFOOLed/Stratide/pull/58#issuecomment-6572130283)，数据本机 ignored 保留；新环境按当时授权/权限/调用和空间上限重新 preflight + 回填，不强制搬运旧 GB 级库。新下载重新计算来源时间、SHA、修订/覆盖/质量，不能冒充旧冻结输入。旧研究复现只依赖仍可访问的原冻结数据。此轮没有迁移、覆盖或删除现有数据，操作说明已补齐。
