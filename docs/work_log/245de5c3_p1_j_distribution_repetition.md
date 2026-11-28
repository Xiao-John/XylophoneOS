# 245de5c3 · P1-J accepted R1 distribution repetition

2026-11-28。本组完成 P1-J 已验收 R1 分发的自动重复流程。两次新目录、独立 UUID
的完整运行均通过，同一冻结 runner 源码为 `dedf69415f1942bcf860b6ec7dd2e211869501e9`；
独立只读 verifier `2a64ff11e0d1dcbcdaaaafd9ecccecc780ea4f47` 的比较结果通过。本组不发布新 Release，不替代首次 R1 资格与公开交付门。
完整数据、串口、失败记录与原始/导出来源位于
[本轮报告](../reports/p1_j_repeated_distribution_20261128/readme.md)。

## 源码与范围

- `6e77aefd46bed1fb8303f6be244b3b430ec1f665`：新增完整 repeat runner、准确输入锁和 host 负例。
- `b63ca741dc34d4831113b772aa10c6025c31fae1`：分开实际可执行载荷与 debug 路径差异，保留两种 debug 身份。
- `edff7cd21ab15742fc41bb1db57f3a565776f0df`：干净快照包含既有 SDK gate 需要的 release 元数据。
- `d56a5976940b49aecd0437bb2ef9fa64a9d3bd39`：先创建现有 guest harness 使用的 runner/build 日志目录。
- `dedf69415f1942bcf860b6ec7dd2e211869501e9`：按真实最后消费者退役临时磁盘，保存全盘摘要和 producer/consumer 报告绑定，冻结再次复核三份退役回执；补三个有意义的生命周期 host 负例/正例。

完成两轮后，原 compare 因复用 XPK 的 8 层解析器而拒绝真实 9 层 run envelope。
只读 verifier 修复为 `2a64ff11e0d1dcbcdaaaafd9ecccecc780ea4f47`：仅 completed report
使用 1 MiB/16 层严格解析，保留 duplicate/UTF8/float 拒绝，补 exact frozen inventory、
每文件 hash、15 immutable 资产跨轮一致与源 tar 实物核验，并记录 verifier 的
commit/script SHA。原 producer 定义 AST 全部不变，未重跑或重写两轮 guest；原
orchestrator failed 与错误日志保留。
[比较失败与修复](../reports/p1_j_repeated_distribution_20261128/comparison_attempts.json)

新增生产入口为 `scripts/repeat_glibc_distribution.py`，输入锁为
`config/release/p1_j_r1_repeat.json`，host 用例为
`tests/repeat_glibc_distribution_host.py`。没有新增 syscall、协议布局、guest ABI，
也未修改公共 registry/state；共享状态由整合者更新。
[命令与契约](../contracts/repeated_distribution.md)

## 两次真实完整运行

| 尝试 | 独立 UUID | 开始（UTC） | 完成（UTC） | 阶段 | 冻结产物 |
| --- | --- | --- | --- | --- | --- |
| 5 | `f645a9f55f014156937bd263bee870de` | 2026-11-28T12:47:10.050213+00:00 | 2026-11-28T13:12:18.274219+00:00 | 14 / 14 | 20 / 430,314,234 bytes |
| 6 | `480ad403fe0f4210a6c5e8ab1975cf26` | 2026-11-28T13:12:46.372359+00:00 | 2026-11-28T13:35:26.465667+00:00 | 14 / 14 | 20 / 430,314,234 bytes |

每轮重新归档 runner 与 R1 native 源、重建实际系统、重链接五套材料中的全部
17 个程序，然后完成 package 3 项、GNU 20 项与五组实际替换客体；接收归档重开、
源码对应、错误 hash、过期 SDK 和缺失 source 门全部通过才 freeze。
两轮冻结文件精确清单与全文件哈希均复核，比较绑定了相同 bundle、工具、SDK、
源码归档、native 输出和全部 receiver 原版/替换版身份。
[比较](../reports/p1_j_repeated_distribution_20261128/comparison.json)

native 源仍为 `819ea63ae84b1e89862648af002c2a09d1936c02`，2,211 个输入逐项匹配，
build `7c8c59058be0b5f1`。普通 ISO、kernel.bin 和 hello ELF 与原 R1
逐字节相同；debug ELF 因 producer/receiver 路径不同而明确保留不同摘要，
不把它描述为全字节相同。工具版本和具体文件身份见
[native rebuild](../reports/p1_j_repeated_distribution_20261128/native_rebuild.json)。

完整 producer tree 同时可从公开 source anchor
`110cb65159af7b43220ed6a76d30a185dd014c77` 取得，tree
`241ed633b8e40c013d093dbc52f1f8b3f18e48ce` 与本地 dedf 完全相同；本组已实际读取两个 Git tree 核对。
原 run 的 producer 字段和 archive 摘要保持不动，remote commit 产生的 tar wrapper
元数据可能不同，不把 source tree 相同冒称为原 archive 同字节。
独立 verifier 另有公开锚 `9420458011f521c342a0f36c5152e8c96ad2a81a`，
tree `be7b30f79342b8073fe94c6283951866248dd924` 与本地 verifier 完全一致，也已实际
读取 Git tree 核对；不能用 verifier 锚替换 producer 身份。
[映射](../reports/p1_j_repeated_distribution_20261128/source_anchor.json)

## 失败与空间问题

1. 早期尝试把含路径的 debug ELF 与 producer 全字节强比，正确失败；随后单列 debug 身份并检查真实 loadable payload/layout/symbols。
2. 第二次快照缺少历史 release 元数据，prepare 失败；补齐原始 Git 文件后使用新目录。
3. 第三次缺少 runner/build，relink guest 阶段失败。后续手工完成尾部仅作诊断，原 overall failed 保留，不能计入两次完整资格。
4. 第四次 package 与 GNU 20 项实际通过，随后 receiver_preflight 重开归档时 ENOSPC；overall 仍 failed。按完整 SHA 回收已关闭盘并保留原报告、串口、错误与清理收据。

新冻结源修复磁盘生命周期后，从两个原本不存在的目录运行第五、六次。
GNU 盘在 combined 结束后、package 盘在 preflight/readback 之后、安装 snapshot
在五组 substitution 结束之后才退役。不能仅看进度 marker 提前删盘。
最终结果迁存前后完整 inventory 与保留文件逐字节复核，原始 run/qualification
路径不改写，临时展开回收另有 receipt。两轮都完整通过后，保留副本中 SHA、大小与
mode 完全相同的 immutable 文件按同 FS 硬链接去重，独立新结果先逐字核验；receipt
单列物理存储共享与 mtime 差异，不以去重冒充 fresh 执行。
[失败记录](../reports/p1_j_repeated_distribution_20261128/attempts.json) ·
[字节保全](../reports/p1_j_repeated_distribution_20261128/byte_conservation.json.gz)

## 验证与未验边界

最终 verifier host suite 21 项通过（含 7 个非法 envelope 子例），producer 原有
15 项在实际两轮运行前已通过；后置保全另有合成 host storage fixture 实际验证。许可检查使用与旧 R1 完全对应的 Git 源和 SDK，10 份材料、
0 active open；现有 deferred/not-applicable 条目保持。最初 sparse docs 和错误
source/SDK 搭配的诊断检查不作为通过，完整 materialization 后才执行文档与历史门。
最终新报告平铺清单、暂存公开路径和完整 docs 门的实际结果在
[validation](../reports/p1_j_repeated_distribution_20261128/validation.json)。
全仓报告门仍有旧 glibc_v2/mobius 清单的既有 17 项失败，本组保留原样并核对前后集合；
不能把本目录通过写成全仓通过。

本轮没有重编所有上游 glibc/GCC/应用源码，没有验收物理掉电或实机 NIC，没有
把旧 R1 结果重绑定到当前 main 的运行库，也没有上传新发行。首次 R1 的升级故障与
新旧 SDK 往返仍引用原资格，不冒称本轮重新执行。复跑应使用契约中的
两个 fresh run 与 compare 命令。compare 在有真实 Git 元数据可访问的宿主源码
checkout 执行，不能把仅映射 /work、外部 common-dir 不可见的 SDK 环境视为等价。
整合时保留上述真实 producer 与 verifier 源锚；如换源码、
SDK、系统或 bundle，按实际受影响范围重新验收，旧报告不能自动转移。
