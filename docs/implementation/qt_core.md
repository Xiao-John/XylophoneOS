# QtCore 当前实现

2026-10-28。QtBase 6.8.3 静态 QtCore 经 PR #8 合入 main（7a7481f）。
本页描述已实现范围；后续路线见[Qt计划](../plans/qt.md)，接口边界见
[Qt协作](../contracts/qt_platform.md)。

## 实现与依赖

- `src/ports/qt6/` 固定官方归档哈希、补丁、平台配置及目标构建工具；同版本宿主 moc/rcc
  生成代码，目标 QtCore 和应用使用 GCC 16.2.0 threading SDK 交叉构建。
- 用户态事件分发器使用单消费者唤醒位、wait_word/wake_word 和绝对单调 deadline，
  支持 posted events、嵌套事件循环、定时器、跨线程唤醒与 interrupt。
- QMutex 争用路径使用真实 pthread mutex/单调条件变量；QThread 正常退出保留 Qt
  finished、DeferredDelete、线程局部清理和 dispatcher 销毁路径。
- QFile/QDir、编译资源和缓冲读取可用范围按冻结配置；文件映射、权限/链接、canonical
  路径及无覆盖 rename 等不支持项明确拒绝。FD/socket notifier 不受理，未实现多源 poll。
- 无新增内核 ABI、服务 op 或 Qt 专属权限；共享 threading 编译入口修正 C++ 头文件隔离。

## 证据与边界

主资格的源码/夹具提交 b090d45、系统 build `48e5e73bcd649f44`、QtCore 归档 SHA-256
`d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3`。
[主资格](../reports/qt_e15_qualified_20261028/qualification.json)记录 G01/G03 受限功能通过；
[补验](../reports/qt_e15_recheck_20261028/summary.json)记录同一运行实现的 16 次客体用例、
48 次阻塞边界投递和 24 次活动定时器 worker 退出，以及定向回归。
原命令、失败记录、哈希和串口材料见[0064](../work_log/0064_qt_e15_qualification.md)及
[0065](../work_log/0065_qt_e15_lifecycle_recheck.md)。

验收仅适用于固定的静态 QtCore、单核 QEMU 和 SDK 输入。内存高水位为采样结果；
完整成员许可/静态分发重链接、绝对峰值、长压力、SMP、直接 pthread_exit 退出 Qt worker、
取消和 QtGui/QPA/Widgets/QML/Quick 仍未验。本次文档整合不产生新组合资格。
E16 首先处理显示输入与跨线程唤醒的组合等待，不能把当前 wait-word 当成 FD/display 多路复用。
