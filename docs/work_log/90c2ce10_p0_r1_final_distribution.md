# 90c2ce10 2026-11-28 · P0-R1 最终 glibc 静态发行组合验收

本轮从锁定源码重新构建 glibc 2.44、GCC 16.2.0 的静态 C++ 运行库，以及实际
随包的 Dash、xypm、13 个日用程序、GNU Make、CPython/zlib 和 IDNA。记录绑定
新候选、实际发行盘、SDK/profile 和接收材料；没有复用之前未获准公开的验收附录。
本记录描述本地技术验收，公开 Release 资产的交付状态单列于
[delivery.json](../reports/p0_release_final_20261128/delivery.json)。本地冻结完成不代表
资产已上传，也不改变已经发布的 newlib 版本身份。

## 实际输入与环境

候选源码为 `3964200d524fd39f3a95c166800832623c5f3591`，普通及安装介质的
系统标识为 `7c8c59058be0b5f1`。该源码包含两个输入维护修复：zlib 原下载地址
失效后改为官方同版本 Release 地址，源归档 SHA-256 不变；随后同步许可台账
登记的锁文件摘要。首次候选正确停在许可门，修复后使用新目录完整重建候选。
两次记录分别保留，见 [attempts.json](../reports/p0_release_final_20261128/attempts.json)。

该系统清单登记的 2,211 项源码已与公开提交
[`819ea63ae84b1e89862648af002c2a09d1936c02`](https://github.com/Xiao-John/XylophoneOS/commit/819ea63ae84b1e89862648af002c2a09d1936c02)
逐项比较，全部 SHA-256 相同；原生产者提交身份保持不变。这个对应关系以及同一
系统的 native launch、IPC、deadline、stdio 和 ABI 门，见已公开的
[最终集成回执](../reports/p0_integration_final_20261128/README.md)。

构建在原 SDK Preview 2 的普通 launcher 中执行。原预发布 SDK 归档 SHA-256 为
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
目标工具为 GCC 16.2.0 / Binutils 2.47，客体使用 SDK 中的 QEMU 11.1.3。
普通 smoke 使用独立提供的 Clang/LLDB 19.1.7 宿主工具；原 SDK 未被改写。
`--offline` 在此宿主因 NETLINK_ROUTE 被拒绝，接收方使用普通 launcher 的独立
工作目录挂载，不能据此声称网络命名空间隔离。静态程序的实际声明范围保持不变。

| 绑定 | SHA-256 |
| --- | --- |
| C SDK manifest | `9bb39b94106b9604d58acc5dc4c78829439c4eba6f456e7afdd270c99a154e22` |
| 最终 C/C++ SDK manifest | `56c596967ff6ec6c51b593e91ff01f3c4bc7ac2903ace6ab426b290b358f4703` |
| 最终 SDK tree | `7ea2166b55e753e1bc194f988bfff11e52bde806061d35fd3a208c3b2ebf16ab` |
| application kit tree | `672bb1543fe545a2c48371f27e84ff262671a57ccd1e93f8bdec087529559152` |
| profile | `437926bf43578493f38ea3c4834e98babebf797ef4e504a914dbbd93bdd9080d` |
| 发行 manifest | `0e97d5f9e563fc33619563af1b35f041e021e507fa1ef1abaabf4354731a188e` |
| 发行初盘 | `c2289ab88c37e0e4e3262a2a2d2f643b75b437370903340d6c336012e3168a9a` |

选定 profile 为 `xos-x86_64-glibc-p0-20261128`，含 C++、目录、线程及 stdio
transfer。SDK 的构建状态与 guest 资格分开记录；后续验收不修改其不可变清单。
C SDK 输入映射与 C++ 构建回执各自保留，不用候选的 Git 标识替代它们的实际
输入身份。[SDK 构建摘要](../reports/p0_release_final_20261128/sdk_builds.json)

glibc 原档、签名和固定发布钥匙完成验证。GCC 归档、签名与 GNU 钥匙环也在
本轮重新验证，14 个 C++ 构建步骤全部成功，包含运行库配置/安装及五个展开器
成员的重建合成。GNU Make 4.4.1 使用本轮固定归档和 GPG 签名构建。
[glibc 验签](../reports/p0_release_final_20261128/glibc_authentication.json) ·
[GCC 验签](../reports/p0_release_final_20261128/gcc_authentication.json)

## 同一套候选与发行盘

| 实测对象 | 结果与界限 |
| --- | --- |
| 普通系统 | `make -o build smoke` 的 79 项检查/组通过；10 份登记许可材料检查通过。许可报告范围仍是登记材料与 SDK 副本，并非法律意见。 |
| 安装 ISO 与 stock | 实际安装器通过外部 ELF、PATH 和 Dash 门；stock guest 完成日用工具包安装、冷启、13 个工具运行与卸载核对。 |
| CPython 与包组合 | 3.14.9 静态解释器、zlib 1.3.2、558 成员标准库和 IDNA 3.20 使用同一 profile。安装及普通冷启执行线程、JSON、gzip、压缩 ZIP、IDNA；原生卸载 daily 与 IDNA 后保留 CPython 和用户文件。 |
| 原生 GNU 工具 | 20 项通过：从客体直接编译/执行 C 和 C++，分别由 Xshell 与 Dash 驱动 GNU Make，拒绝未定义符号，冷启后重跑程序与 Python 发行脚本。应用链接使用所选 glibc sysroot。 |
| 接收方归档 | 重开四份基底归档，核对 GNU Make 签名；缺项、重复、改字节、多余成员和不完整 Seed 参数均被拒绝。包回收后 1,515 个 GNU Seed 文件保持原摘要。 |
| 对应源码 | 组件源归档的 140 项核对通过，绑定实际包、补丁、构建输入、sbase Git tree、安装器和 CPython/zlib 回执。GNU Seed 对应材料与 glibc 上游原档单独随发行集合保存。 |

GNU Seed 的 GCC/G++/Binutils 驱动沿用公开冻结供体，保留其历史静态运行库身份；
本轮 guest 的应用链接使用选定 glibc sysroot。新 C++ SDK 的 GCC 16.2.0 源归档、
签名及钥匙环应与新宿主 SDK 的源码材料一同交付，不能用历史 Seed 源包代替。
[组合客体](../reports/p0_release_final_20261128/combined_guest.json) ·
[归档重开与负例](../reports/p0_release_final_20261128/preflight.json) ·
[源归档清单](../reports/p0_release_final_20261128/component_sources.json)

## 全部 17 个 glibc 静态程序的接收方重链接

五个独立接收目录分别只提供材料归档和对应 receiver 脚本，通过原 SDK 的工具
重链接。原程序逐字节匹配发行产物；CPython 同时核对调试 ELF 和实际去调试
运行 ELF。每种替换保留 libc.a 的 1,687 个成员及顺序，只改变一个成员。
全部五组错误替换归档摘要均在产出前拒绝；xypm 另验证错误材料清单摘要拒绝。

| 程序 | 替换与真实 guest 验证 |
| --- | --- |
| xypm | 替换 `ioputs.o`，仅在版本行输出诊断标记；原版和替换版各运行 `--version`、`list`，实际安装器盘中的 xypm 与发行字节一致。 |
| Dash | 替换 `getpid.o`，使测试 shell 的 `$$` 出现指定值；真实安装器写入的 shell、普通客体执行及外部程序均被核对。 |
| 13 个 daily 工具 | 替换 `exit.o`，每个工具输出一次结束标记；实际安装后运行原版、替换后冷启再运行，各工具内容输出相同。 |
| GNU Make | 替换 `exit.o`；原版与替换版分别通过版本、Xshell 构建、预期退出 2 的失败配方和 Dash 构建，落盘结果核对一致。 |
| CPython | 替换 `exit.o`；使用实际 XPK 标准库运行原版和替换版，输出及落盘内容一致并观察结束标记。 |

各 guest 恢复其资源基线，适用场景为 `129793 / 2 / 0`。
接收归档摘要、成员比较、ELF 摘要、负例与五组原始日志摘要在
[receivers.json](../reports/p0_release_final_20261128/receivers.json)；每组 guest
报告位于同一平铺证据目录。原始串口和 receiver 日志本地保留，其原始摘要在
结构化回执中；本 PR 不附带这些日志。

xypm 的五个翻译单元从发行项目回执重编，重建 ELF 与 stock 完全相同后才收集
对象和链接顺序。Dash 默认 Automake 日志为静默模式，第一次收集按缺少链接行
拒绝；随后在同一配置、同一对象上实际执行 `make V=1 -W main.o dash`，确认其
输出仍与安装器 Dash 逐字节相同，再使用这份实际链接日志收集材料。没有伪造
链接命令，也没有修改发行安装器或 SDK。

## 升级、恢复与冻结 SDK 往返

在同一发行初盘副本上，IDNA 测试修订于同步检查点 123 中断，留下未提交
journal。内置恢复器把原数据库、索引与用户数据逐字节恢复；发行 xypm 重试
成功，冷启后 Python/gzip/IDNA 和 58 个受管文件核对通过。故障构建与正式
xypm 的 22 项输入中 21 项相同，唯一差别为 `main.cpp` 的测试开关；工具链、
SDK、profile 与 backend 相同。物理掉电和扇区撕裂没有测试。
[升级回执](../reports/p0_release_final_20261128/upgrade_guest.json) ·
[故障构建对照](../reports/p0_release_final_20261128/fault_build_comparison.json)

使用公开原版 0.0.1-1024 的 SDK、媒体和独立数据盘，执行四次真实冷启动：旧版
基线、选定 glibc、回退旧版、恢复 glibc。六次普通程序执行均退出 0，15 个
SDK/profile/未标记盘保护检查通过。两个工作盘中的用户文件分别保留并追加
预期内容，冻结 XPK 重打包得到同字节，原始输入不被改写。
[完整往返回执](../reports/p0_release_final_20261128/frozen_roundtrip.json)

## 复跑与交付

从干净源码和明确的锁定归档开始，使用 `glibc_release_pipeline.py` 的
`build`、`package`、`components`、`materials`、`smoke`、`gates`、`freeze`
阶段。包构建和材料收集的完整参数约束保留在工具帮助与
[既有流水线说明](../releases/glibc_pipeline.md)；本轮输入与输出摘要全部在
[证据索引](../reports/p0_release_final_20261128/manifest.json)。

```sh
python3 scripts/glibc_release_pipeline.py build \
  --output "$XOS_CANDIDATE" --glibc-app-kit "$XOS_KIT" \
  --glibc-daily-source "$XOS_SBASE"
python3 scripts/glibc_release_pipeline.py package \
  --release-dir "$XOS_RELEASE" --glibc-candidate "$XOS_CANDIDATE" \
  --glibc-app-kit "$XOS_KIT" --cpython-package "$XOS_CPYTHON_XPK" \
  --wheel-package "$XOS_IDNA_XPK" --gnu-seed-donor "$XOS_FROZEN_SEED" \
  --gnu-make-receipt "$XOS_MAKE_BUILD/manifest.json" --gnu-make-sources "$XOS_SOURCES"
python3 tests/glibc_gnu_seed_release_preflight.py \
  --release "$XOS_RELEASE" --output "$XOS_PREFLIGHT" --guest-dir "$XOS_RAW_SMOKE"
python3 scripts/glibc_release_pipeline.py freeze \
  --release "$XOS_RELEASE" --supplements "$XOS_SUPPLEMENTS" \
  --smoke "$XOS_PUBLIC_SMOKE" --sdk-state "$XOS_SDK_STATE" --output "$XOS_FROZEN_OUTPUT"
```

`XOS_CANDIDATE` 必须是源码树内 `build/candidates` 下的新目录，`XOS_RELEASE`
必须在 `build/releases` 下。接收脚本各自接受 `ARCHIVE ARCHIVE_SHA256
MANIFEST_SHA256 OUTPUT` 四项，在只挂载其材料的新工作目录内执行。五组 guest
脚本绑定发行摘要、原版/替换版摘要以及实际安装盘；这些测试不改发行原盘。

最终 v6 补充集合包含全部五组重链接材料、组件源和 glibc 原档；原子 freeze
另绑定三个同盘组合报告与 glibc/冻结 newlib 两个 SDK 身份。
冻结状态为 `assembled_static_distribution`，共 20 个文件、430,316,403 字节；
其中 19 项列入其校验表，另一个文件就是校验表本身。原来的 15 项基底/补充资产
字节未变。三个 smoke 报告使用明确标注原始摘要的公开副本；只抽象命令/输出的
路径展示，再让 combined 报告绑定两个导出报告的摘要。检查结果、case 数、
系统/SDK/包/盘身份和程序产出摘要保持原值。预检读取含实际工作盘的
`XOS_RAW_SMOKE`，freeze 使用这三份已核对的 `XOS_PUBLIC_SMOKE` 副本。
[导出绑定](../reports/p0_release_final_20261128/smoke_publication_binding.json)

外层 `p0-r1-glibc-release-20261128.tar` 仅含 20 项冻结文件、README、外层
manifest 和外层校验表；没有追加 raw 串口、调试日志、私钥或旧附录。内层不可变
源/构建材料及原公开 GNU 供体仍保留其必要的历史/固定工具链路径，不能宣称对
这些二进制与源归档做了无损路径清除。外层共 430,346,240 字节，SHA-256 为
`492c7b311431132398b84f62ff9357f516983039094559d41d4159e3e7e19ff4`。

新的宿主 SDK 打包与外部消费者验收单独记录，不能把源树里的 kit 自动当成
已经解包验证过的宿主 SDK。Actions 独立重建的默认包 profile 也不能与 R1
profile 互换；制作本发行盘的 XPK 应显式调用本 bundle 的 `application-sdk/xos-app`。
许可台账保留 1 个 deferred 与 7 个 not-applicable 条目的原范围，0 个 active
open 不等于所有许可问题已解决。动态 generation/startup 由 R2/R3 的正式报告覆盖；
本静态发行记录不声称任意 `dlopen`、全量 POSIX、未随包 CPython 扩展或 GUI
资产通过。链接器已报告的 GNU 占位接口也没有被扩写为支持。公开副本对宿主路径
做显式变量抽象，并同时保存原始与导出字节的摘要；不可变发行资产保持原字节。

公开前的实际暂存区路径检查为 `PUBLIC_READY`，0 项 `OPEN`、0 项 `UNVERIFIED`。
两项 `DOUBTFUL` 已独立逐字段复核：daily 的临时文件和 GNU 客体编译器的临时
对象都是真实 guest 路径，保留其原值。平铺索引的 32 项逐字节校验全部通过。
全仓 `report_manifest_check.py` 将本目录登记为 compliant；该命令的整体结果在
本分支基线上仍受旧 `glibc_v2_*` 与 `mobius_*` 报告的既有清单格式问题阻断，
本组没有改写这些历史冻结报告。工作日志编号由标题生成器得到 `90c2ce10`，外层
README 的引用随之修正；重打外层时仅该 README 与外层校验表改变，20 份冻结
输入逐项保持原摘要。
