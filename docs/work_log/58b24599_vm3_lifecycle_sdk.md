# 58b24599：VM3 生命周期与 SDK 恢复记录

基线 `2b2816b`。原执行环境被替换，原本地提交 `4370d3b` 和其测试
产物不可访问；本次重新实现，不将旧报告改绑到恢复后的源码。

已恢复分批页表复制与回滚、单线程 fork 续体、匿名 VMA 的 fork/exec
生命周期、公开 sys67 和受限 mmap/mprotect/munmap。重新构建的工具链为
GCC 16.2、Binutils 2.47、NASM 3.02 和 QEMU 11.1.2。

恢复后的实际客体验证包括：VM1 保留区；VM2 页权限故障、取消和全部
4096 个页分配失败位置；VM2 续体和线程 pin；VM3 fork/exec、两轮
分配失败回滚和 fork 取消；公开 SDK 的 xsh/dash 映射和实际页故障；
线程 SDK；E04 和 T0–T2；QtCore、QtGui 和 Widgets 定向测试；以及
CPython T3 锁、线程、阻塞 I/O 和退出。相关报告记录镜像摘要、构建
标识和资源基线。Qt Widgets 保存、键鼠、截图和资源回收均有客体验证。

报告绑定的镜像构建标识不同：VM2 扫描为 `e9100a5f68942f5b`，VM3
生命周期重验为 `03b9da4732803ba4`，Qt Gui/Widgets、CPython T3 和
公开 libc 定向测试为 `f373f28f75c0638f`。核对五个恢复镜像清单中
全部 177 个 `src/kernel/`、`src/shared/` 和 `src/user/` 源文件摘要，
这些源文件一致；镜像仍须按各自的构建标识追溯，不把报告改绑。

QtCore、Gui 和 Widgets 库与 XOS 定向程序已构建并验证，但完整 Qt
`ninja` 在额外的 minimal 平台插件因缺少 Unix 私有头文件而失败；
不能把此结果写成完整 Qt 构建通过。以上测试也不单独构成全部 V1–V7
退出条件的正式资格结论；SDK manifest 的 `vm_extensions` 保持
`implemented_unqualified`，后续仍需按合同逐项核对完整覆盖和证据。
