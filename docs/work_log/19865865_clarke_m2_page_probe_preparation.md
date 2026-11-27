# ClarkE M2 本地整页夹具准备

2026-11-27。基于无 JIT 编译修复和回执 `f14851ca`，夹具提交
`19865865` 和客体回执检查 `ac273690`。独立编译
`tests/fixtures/webkit/local_page.cpp` 时，GCC 对 `LocalFrame::view()` 和
`LocalFrame::document()` 发出缺失内联定义警告，目标 `nm` 确认对象引用
两者的未定义符号。夹具加入上游定义所在的 `DocumentView.h`、
`LocalFrameInlines.h` 后，以 WebCore 的真实目标编译选项重建。目标对象通过
ELF 类型检查，且不再引用这两个未定义符号。上游 `TestPage.cpp` 以相同目标选项编译。

客体回执现在绑定完整软件源锁。用仅软件源锁摘要错误的回执做宿主负向验证，
运行器在创建客体输出目录或启动 QEMU 前拒绝该输入。

从 `ac273690` 重建普通系统 `973a42691eb63930`，并逐项核对
1,991 个 manifest 源输入。许可审计通过 10 项。在独立 FAT 工作盘上启动
QEMU 至 xsh，停止演示任务后资源基线为 `129709 / 3 / 1`。这一步覆盖承载镜像
和工作盘前置条件。

| 工件 | SHA-256 |
| --- | --- |
| 夹具目标对象 | `40c1a0dbdf47cf85da2b41a73084984c140bef08c6ca72f887b615f0260c3b50` |
| 上游 TestPage 目标对象 | `2da371ad51ecb02237360b63fbd071b22b8ed790aa742c2dc3e7d9fec4d93bd7` |
| 系统 manifest | `63bafc0b4ebc1201405b6b8e2d0d38a86256bf812ba9fae9fa490bb9f11ea4d7` |
| 系统 ISO | `bfbb71ee0eda3737ff4021b862b1bb3853c41ba6dfc4edbc54c33b6ba883ca4f` |
| xsh 启动串口回执 | `334e8549b5c80e43729aa79ef241fcce373e6b8ae0a3eb75c9b9826818eab9f8` |

## 同配置 JavaScriptCore

同一软件 WebCore 配置已生成有 649 个成员的 `libJavaScriptCore.a`。
使用该配置的原生 JSC 命令编译 shell，并按 CMake 的链接项和 glibc 静态 SDK
组装 x86-64 `ET_EXEC`。查验了独立 RX、R、RW 段和 TLS 段。
QEMU 11.1.2 在上述系统镜像的 xsh 中运行锁定的普通脚本，输出
`CLARKE_JSC_LLINT_PASS 6,15,36` 并退出 0，前后资源均为 `129709 / 3 / 1`。

| 工件 | SHA-256 |
| --- | --- |
| JavaScriptCore 静态归档 | `907192d0ec38fc5e1e2782ffe75b7731139df11f26039650ad527182cd42badf` |
| 同配置 JSC shell ELF | `db7cdb617e58de07334351c7904a38ac4aaf3cc8599279c8410cb0c7ed288524` |
| JSC shell 客体报告 | `5ed7881e0090fc129e907612e385957b9158ababf51f967a3653ac48f8451aec` |

## 同配置 Test262 和 PAL 归档

用同一 JSC ELF、系统 ISO 和锁定的八份同步 Test262 用例复跑既有客体
运行器。22 个写入 FAT 的工件全部读回核对。严格和非严格模式合计
16 次均退出 0，完成标记各出现一次，资源恢复到 `129709 / 3 / 1`。
首轮进程中断时只留下空 QEMU 日志，本记录使用后续完整复跑。

用同一 CMake 链接图的 12 个实际目标对象生成单独的 PAL thin archive，
并用目标 OpenSSL、ICU、WTF、bmalloc 和静态 glibc SDK 链接
`pal_digest.elf`。初次尝试在另一挂载目录生成 thin archive，成员路径
无法解析。改用与构建图相同的目录后归档成功，并补上 WTF 所需的 ICU
归档。客体对 `abc` 分段计算四种摘要，退出 0，资源前后一致。链接器
仍报告 `madvise` 和 `raise` 为未实现项，该场景不覆盖这些路径。
[归档、链接与客体回执](../reports/clarke_webcore_archive_preflight_20261127/manifest.json)

完整 WebCore 归档正在构建，四路并行编译时有一个 JSBindings 编译进程
被宿主虚拟机的内存不足处理终止，内核记录其匿名 RSS 为
`2061204 KiB`。保留运行中的 Ninja，从同一 CMake 编译数据库取出
`UnifiedSource-JSBindings-10.cpp` 的命令，仅替换输出路径，单独在
最多 3 GiB 的容器中复编。目标 x86-64 可重定位对象大小为 13,567,000
字节，SHA-256 为
`1db3195ed09125d18767edf331162511da9048cec735d5b952be5474036bbe8e`。
该复编产物与全量 Ninja 输出分开保留，归档构建还须通过原图的该节点。

## 峰值主机空间

从 Ninja 日志取 464 个已完成的 WebCore 目标对象，分配空间为
557,002,752 字节。以相同的 GNU `ar crT` 规则在临时内存盘归档，
索引和成员引用占 102,148,012 字节。按已完成的平均索引大小对 2,205 个
目标对象作线性外推，完整 thin archive 约为 463 MiB。剩余编译对象按
近期样本和全样本外推约需 1.0–1.95 GiB。实际链接产物另计。

以同配置 JSC shell 实测 `--print-map | gzip -n -3`。ELF 与原始
验收工件逐字节一致，链接表由 290,518,599 字节降至 17,604,045
字节，解压后可独立校验原文。整页链接沿用此方式保留完整链接表。
客体 runner 的稀疏 FAT 和 ELF 读回临时文件在内存允许时置于
`TMPDIR` 指定的 tmpfs。以现有 JSC ELF 尺寸计算，两份暂存数据约为
235 MiB，正式 WebCore ELF 的实际大小待链接确认。

归档完成后按
[软件 WebCore 门禁](../../src/ports/webkit/page/README.md)链接实际
`local_page.elf` 并运行两个 HTML 用例。整页链接、DOM、CSS、绘制与退出回收
尚待这次客体核验。

## 存储停线与原图续编

原四路 Ninja 在第 1,768/2,383 条边后触发宿主存储保护，记录可用空间
783,007,744 字节。仅中断 Ninja，退出码 130。宿主与 Linux 在恢复前独立
校验原路径，确认冻结源码 39,117 个条目和构建图 16,088 个条目的文件摘要、
时间戳与符号链接一致。只读下层和 3 GiB tmpfs 上层保留原 CMake 路径以及
Ninja 日志。余下 618 条边以两路并行接续。

两条历史内存失败边均由正式 Ninja 编译并登记到上层日志。`JSBindings-10`
与早先的独立对象逐字节一致。`inspector-21` 的 x86-64 可重定位对象为
4,540,864 字节，SHA-256 为
`2bc7e6bdf5b63f3cc2ccae99a2f939b5a966776b1946120be74d5af277b23cdd`。

## 软件图像编码编译边界

续编报告 `UnifiedSource-platform-226.cpp` 缺少 `GLContext.h`。
`raster_image_encoding.patch` 将 XOS 软件配置的纹理编码输入返回为空，
并在栅格路径直接包含 `SkPixmap` 声明。其它平台沿用上游加速编码路径。
用 GNU patch 零 fuzz 应用到隔离副本，使用该统一编译单元的原配置命令得到
192,208 字节的 x86-64 目标对象，SHA-256 为
`37d82c6bbbb1854e0f89fa45c98c2590072c9721def44ae366b8d3b93e205e05`。
符号检查确认该对象调用栅格 JPEG、PNG、WebP 编码入口，未引用 GL 上下文、
显示对象或加速编码入口。当前软件 Skia 归档提供三个编码器的上游
`*_none` 实现，实际编码能力尚未验收。原源码保持冻结，锁定补丁待正式
Ninja 回合结束后纳入归档重建。

## CSS 自定义函数登记编译边界

Style 阶段的 `UnifiedSource-style-6.cpp` 单独包含
`CustomFunctionRegistry.cpp`。该文件使用 `WTF_MAKE_TZONE_ALLOCATED_IMPL`，
此前依赖其它统一单元间接包含宏定义。补丁显式引用
`<wtf/TZoneMallocInlines.h>`。用 GNU patch 零 fuzz 应用到隔离副本后，
原 CMake 交叉命令生成 319,256 字节的 x86-64 可重定位对象，SHA-256 为
`67df50ff54d6f12ad09fc1eb6a81261a5cf0f6be165c922b3dbc6232edce6ab3`。
对象保留 `registerFunction` 和 `functionForName` 定义。CSS 运行行为随整页
客体验收，本次实际执行范围为单元编译和符号检查。
