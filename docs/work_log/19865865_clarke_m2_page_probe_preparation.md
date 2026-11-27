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

完整 WebCore 和 PAL 静态归档正在构建。归档完成后按
[软件 WebCore 门禁](../../src/ports/webkit/page/README.md)链接实际
`local_page.elf` 并运行两个 HTML 用例。整页链接、DOM、CSS、绘制与退出回收
尚待这次客体核验。
