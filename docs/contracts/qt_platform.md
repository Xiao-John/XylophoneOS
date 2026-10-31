# Qt移植与系统底座协作契约

2026-10-28。接口责任与需求登记；受限 QtCore 客体资格见下文，不冻结尚未设计的C函数/ABI。
Qt具体版本、模块、feature、工具和资源预算在G01确定，不能把本契约当作任意Qt版本保证。

## 责任登记

| 能力 | 提供方/当前状态 | Qt侧责任与下一个验收 |
|---|---|---|
| C++/pthread/TLS | 工具链/线程线；T0–T2、T3-PY和Qt QThread受限测试有各自证据 | Qt配置与QThread/互斥/条件/退出探针；不复制第二套线程库或空锁 |
| 单调/墙钟 | 时钟SDK；单调等待与PY3 B2墙钟已有受限证据 | QtCore计时/超时与实际分辨率，唤醒deadline不被墙钟调整替换 |
| 事件就绪/唤醒 | QtCore受限 posted event/单调计时与跨线程唤醒已客体验证；通用多对象poll/select未实现 | E16 通过锁外阻塞输入线程、Qt queued wake 组合；无通用 poll/select，不忙轮询或假报 FD 就绪 |
| 显示/输入 | 显示线；display_client、65/66、单surface/焦点、CPU raster与PS2 | QPA integration/screen/window/backing-store/input；读取实际mode/stride，客户端RAM呈现，不直接MMIO/BIOS |
| 内存/映射 | 内存线；堆/页预算已有，VMA/mmap/mprotect未实施 | 列实际调用与合法回退，提交最小失败探针；不从Qt侧另加内核mmap特例 |
| 文件/路径 | 文件服务+libc；现有受限FD/路径，权限/链接/完整locale未完成 | QtCore读写/资源/错误，明确ASCII路径边界；UTF-8内容不代表Unicode文件名合规 |
| 网络/终端/动态装载 | 各底座专项；无完整兼容资格 | 首窗不强制全量实现；关闭feature须可见并按实际消费者记录，不伪造成功 |
| moc/rcc/uic等生成器 | 移植线 | 首轮可同版本宿主生成、交叉构建；目标端重建另验G10，不混淆执行地 |

## 接口边界

- 内核只提供通用机制，不包含Qt类、对象名、程序名特权或Qt专属syscall。
- 用户态QtCore平台适配与QPA插件由移植线维护；现有src/ports/下新Qt目录在选型开工时建立。
  显示服务/SDK由显示线维护，pthread由线程线维护，公用libc/dispatch由整合负责人维护。
- SDK可用能力必须有版本/尺寸/布局、返回约定、错误与取消/超时、对象生命周期、线程并发
  和配额说明；具体ABI在提供方专项设计冻结。本表的“需要”不能直接当作头文件声明。
- 显示调用前完整校验源缓冲/区域；Qt不得假设零拷贝、直接Framebuffer映射或任意多窗口。
  输入序列/丢失重同步、焦点、客户端/服务死亡与等待唤醒沿用显示契约。
- 请求改变单surface、等待方式、共享映射或对象撤销语义时，先列新契约和旧消费者影响，
  不在QPA补丁里暗改底层行为。不要用新编号绕过必要的兼容与身份检查。

## 并行工作流程

1. 开工在state登记责任角色、分支、文件范围与最小gate；没有登记不能推定其他agent活跃。
2. Qt移植只修改端口/平台适配/自身构建与夹具；缺底座能力时提交调用点、输入、错误及预期。
3. ABI编号与服务op按abi_registry.md先登记，公共头/manifest/dispatch由对应负责人整合。
   号段预留防止跨模块重号，同段内仍需逐项登记；不抢PID/endpoint固定值。
4. 各自私有输出目录，SDK/构建输入固定；共享build排他。旧G02/T2/Python结果只佐证其原输入。
5. QtCore G03、首窗G04、Widgets G05、QML G06、Quick G07分别验；未实现/未运行/失败明确区分。

E15 已由 PR #8 合入（7a7481f），E16 已由 PR #9 合入（be1e9c1）；新组合须独立记录输入与验收。

## E15 受限实现与资格

`codex/qt6-e15` 使用单消费者 coalescing wait-word 分发 posted events 和单调定时器；
FD/socket notifier 拒绝，不能与显示等待复用。QMutex 使用 pthread 单调条件变量；
QThread 取消、映射、路径 canonicalization、UID 权限及无覆盖 rename 不支持。
源码、竞态/生命周期限制与客体候选证据见 [0063](../work_log/0063_qt_e15_continuation.md)。
G01/G03 已受限功能通过，见 [0064](../work_log/0064_qt_e15_qualification.md)；绝对峰值和发行审计未完成。不据此开放新 ABI 或声明 poll 支持。
同一冻结实现的阻塞边界投递、伪唤醒/绝对deadline及活动定时器线程退出补验见
[0065](../work_log/0065_qt_e15_lifecycle_recheck.md)；未扩展公共机制或更改ABI。

## E16 受限 QPA 契约

Qt 6.8.3 静态 `xos` 平台插件：真实 mode/stride、RGB32 用户态 QImage、QRegion
裁剪与同步 Display Service present；无 MMIO 映射/程序名授权。一个独占全屏 Surface，
第二个窗口 connect=-16 后明确诊断并退出；非零 offset/子窗口 flush 不支持。

同一 display_client 的请求/回复事务用 QMutex 串行。输入线程是 SDK joinable pthread，
`wait_input()` 不持该锁，读取后向 GUI 线程的 QObject 投递任务，由 GUI 线程调用
QWindowSystemInterface。退出先置停止、disconnect 唤醒，再 pthread_join，最后清
投递目标；服务死亡以 -19/退出码72处理，重新启动服务后新客户端可恢复。正常共两线程，
仍受每进程4线程限制。没有扩大 syscall65/66 或 display wire v1。

Qt 6.8.3 当前 QThread::wait 的 detached 清理通知可早于内核线程退出；E16 不改变 E15，
输入线程使用 pthread_join 取得完整回收保证。隐藏窗口产生 Qt 焦点退出并抑制 GUI 输入，
独占 Surface 直到窗口销毁才撤销。Set1 英文及 Shift/Ctrl/Alt/Caps、鼠标三键、序列、
64项溢出 resync；无 IME/滚轮/USB/多窗口合成。字体为原版 DejaVu 经实际 FreeType/
HarfBuzz/QPainter 路径。实现、失败与资格见 [E16实施](../plans/qt_e16_execution.md) 和
[0066](../work_log/0066_qt_e16_qualification.md)。静态发行/逐成员许可审查仍未完成。

## E17 Widgets / Aurora 受限契约

使用同一份新构建的 SDK/C++ 运行库交叉编译 Core/Gui/Widgets，冻结 QtBase 6.8.3；
不混用旧 E15 归档。E15/E16 原构建入口与冻结报告保留。Widgets 的非原生子控件、
viewport 和滚动实测使用顶层 backing store、零 offset；现有 child/native、非零
flush offset 和第二顶层拒绝语义不扩展。QPA 仅补 Home/End/PageUp/PageDown/Delete
Set1 映射和 flush 观测；没有新 syscall 或 display wire 变更。

`libXosAurora.a` 提供 `aurora::initialize(QApplication&)`，选择 QProxyStyle/QPalette
及标准按钮/文本/输入的深色样式；canvas/panel/button 为可选共享控件。有限低频模糊、
环境混合和软件指针都在该应用内完成，不是系统合成器、跨应用折射或 GPU 加速。
QtGui 的图像/绘制线程池可多占一个线程，实测常见为3线程，仍受4线程配额；不是把
E16 的两个线程结论照搬到 Widgets。正常/kill/fault/服务故障后的进程资源已核对。

保存复用文件 wire-v2 的 staging/journal。只读以非截断可写 open + close 检查；
QFile 用于读/核对，不用 WriteOnly 截断目标；QSaveFile 不构成安全覆盖承诺。
precommit 错误保留原目标；commit/final sync 错误为 UNKNOWN，保留缓冲并阻止重试。
消费者旧内容比较不是并发 CAS；不宣称所有错误都保留旧路径、任意断电或扇区撕裂安全。
实际错误路径、注入层级、重启字节比对及局限见 [0078](../work_log/0078_qt_e17_aurora_qualification.md)。

G05/Aurora 仅对冻结夹具和已声明范围通过；静态分发/完整许可/重链接、绝对峰值、
CPU、长期压力、完整 Unicode 字体、IME/剪贴板、QML/Quick 均没有继承资格。
复现见 [E17 实施](../plans/qt_e17_implementation.md)。

## 2026-10-30 Aurora v2 / application-local SSG

The opt-in static Aurora library now has tokens v2, native materials, accessibility
and quality fallback, independent standard-Widgets consumers and an app-local
SSG/Intent prototype. See [SDK work log](../work_log/0102_aurora_ui_v2_sdk.md),
[SSG contract](semantic_scene_graph.md) and [consumer qualification](../work_log/0103_aurora_ssg_consumers.md).
No QtCore/Gui/QPA source, system ABI or kernel file changed. Legacy non-Aurora
Widgets remain byte-identical to the archived E17 probe and run on the new image.
The E17 dark Canvas/Panel consumers have not acquired global live theme migration.
