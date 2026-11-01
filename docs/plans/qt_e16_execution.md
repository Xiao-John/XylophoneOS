# E16 QtGui / XOS QPA 实施与复现

E16 从上游 PR #8 的实际 HEAD `d1e108d8f31ffcb1ebf43b40a412af933fb074cd`
建立独立 `codex/qt6-e16-qpa` worktree。启动时上游 main 为 `244ac40`，E15 开放、
非 Draft、未合并且无 review。E15 随后 squash merge 到 `7a7481f`，树与 `d1e108d` 完全相同；E16 已重放到该实际 main，只提交 E16 差异。

## 构建输入和配置

QtBase 6.8.3 / v6.8.3 / `c07c2d5a527a644d36e7853d55132ae38921682f`，官方 archive
SHA-256 `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`。
`prepare_gui_source.py` 先执行原 E15 的七项补丁和运行时复制，再应用独立 0008。
`prepare_source.py`、`configure_target.py`、E15 事件分发器和冻结 QtCore 保持原样。

`configure_gui.py` 开启静态 Gui、捆绑 FreeType 2.13.3 和 HarfBuzz 10.4.0；关闭
OpenGL/EGL/Vulkan、XCB、Fontconfig、设备输入后端、Widgets、网络、动态装载和
poll/select。没有 X11/Wayland 或宿主 Qt 窗口。QtGui 仍包含若干未验 API，编译入库
不等于它们获得功能资格。完整有效 feature 清单在冻结报告中。

FreeType 的 Unix 文件后端需要缺失的 sys/mman.h；0008 选择其原生标准 C 缓冲读取
后端，未制造 mmap。0008 同时排除不适用于 XOS 的 Unix GUI 分发/服务源码。
HarfBuzz 构建清单遗漏的原有 graph/gsubgpos-context.cc 由 0008 补入，完整 Qt 归档符号
闭包最终仅剩链接器提供的 `_GLOBAL_OFFSET_TABLE_`；实际 ELF 无未定义符号。
QPA 字体数据库从 rcc 资源读取原版 DejaVuSans 2.37，通过 QFreeTypeFontDatabase、
Qt 字体匹配、HarfBuzz 和 QPainter 绘制文字。字体不修改、不自研替代字符路径。

以下变量均为绝对路径；E15 构建输入可只读复用，所有新输出使用新目录：

```sh
python3 src/ports/qt6/prepare_gui_source.py "$QT_ARCHIVE" "$NEW_QT_SOURCE"
python3 src/ports/qt6/configure_gui.py --source "$NEW_QT_SOURCE" \
  --build "$NEW_GUI_BUILD" --sdk "$E15_THREAD_SDK" \
  --binutils "$TARGET_BINUTILS" --host-qt "$HOST_QT_683"
cmake --build "$NEW_GUI_BUILD" --target Gui --parallel 4
python3 src/ports/qt6/build_gui_fixture.py \
  --source tests/fixtures/qt6/gui_demo.cpp --sdk "$E15_THREAD_SDK" \
  --qt-build "$NEW_GUI_BUILD" --qt-source "$NEW_QT_SOURCE" \
  --core-build "$E15_CORE_BUILD" --host-qt "$HOST_QT_683" \
  --binutils "$TARGET_BINUTILS" --output "$NEW_APP_DIR/qt_demo.elf"
python3 scripts/build.py --output-dir build/qt_e16/NEW_SYSTEM
```

需要 GCC 16.2.0、目标 as/ld、同版本宿主 moc/rcc、CMake/Ninja 在 PATH。
链接器以 `--no-undefined` 链接实际 CRT、SDK 和 Qt 依赖；显式导入静态 QPA 插件。
Gui 构建产生的 Core 不是应用使用的 Core：应用强制检查并链接冻结 E15 QtCore
`d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3`。
构建回执记录实际命令、依赖、资源、ELF 和工具哈希。路径不能替代回执中的哈希。

## QPA 与线程生命周期

`qpa/qxos.cpp` 针对冻结 6.8.3 私有 API，实现 integration、screen、window、
backing_store、字体数据库以及 GUI 分发器。screen 读取实际 mode；一个独占全屏
Surface。backing_store 只持有普通用户态 QImage RGB32，小端 B/G/R/X；绘制后按
裁剪后的 QRegion 同步提交 Display Service。设备 stride 与源 stride 分别处理。
子窗口/非零 flush offset 显式拒绝；第二窗口的 connect 返回真实 -16 后诊断退出。

GUI 分发器组合原 E15 QEventDispatcherXos，在其前后处理窗口系统事件；主线程仍
通过原 wait_word 等待 posted events/定时器。输入使用一个 SDK joinable pthread：
锁外阻塞 wait_input，锁内完整 input 事务，再以 QObject queued invocation 投递到
GUI 主线程。QWindowSystemInterface 的键鼠分发仅发生在 GUI 线程。呈现与读取串行，
没有持锁的无限输入等待，也没有新增 syscall/服务操作。正常应用共两个线程。

销毁先置停止标志，串行 disconnect 撤销 Surface/焦点并唤醒输入等待，然后
pthread_join 等待 TLS 和内核栈真正回收，最后销毁 QObject 投递目标；旧投递不会
访问已销毁 window。服务死亡返回 -19，主循环以 72 退出。故障/kill 由原进程机制回收。

首版 QThread 输入实现遇到真实竞态：Qt 6.8.3 的 detached pthread 清理通知可先于
内核线程退出，QThread::wait 返回后立即采样曾仍有两线程/两栈。失败保留，改用现有
SDK joinable pthread；不修改 E15 或放宽资源判据。QtCore 的这种瞬时等待边界不能
据本次 QPA 修复宣称已在整个 Qt 中改变。

Set1 键映射支持英文、Shift/Ctrl/Alt/Caps、方向键、press/release；保留输入序列和
单调时间。resync 释放本地 held keys，采用按钮/修饰快照，防止溢出后卡键。
只承诺独占全屏，hide 产生 Qt 焦点退出并丢弃隐藏窗口的输入；销毁才撤销独占 Surface。

## 客体应用和验收

应用使用真实 QGuiApplication/QWindow/QBackingStore/QPainter/QTimer。默认 `hold`
显示矩形、线条、文字、输入反馈和局部动画；释放 Escape 退出。
诊断参数为 `auto/repeat/focus/idle/oom/quota/fault/second/pixels/overflow`；正常输入
字母 P 不触发暂停，只有 overflow 探针允许暂停真实输入消费者来制造硬件队列溢出。

```sh
QEMU=/absolute/qemu-system-x86_64 python3 tests/qt6_gui_acceptance.py \
  --image build/qt_e16/NEW_SYSTEM/xos.img --payload "$NEW_APP_DIR/qt_demo.elf" \
  --case pixels --output build/qt_e16/NEW_PIXELS
```

分别运行 `pixels`、`interactive`、`lifecycle`、`no-vga`；输出目录必须不存在。
夹具创建临时 FAT 盘，通过串口加载目标 ELF，通过 QMP 注入真实 PS/2，读取真实
显存和 scanout；pixels 在客体用 QFile 导出 QPainter 的 QImage，停机后才读取该
参考文件，与显存逐行全字节比对。宿主不写 framebuffer、不调用客体事件处理函数。
每次保存失败、串口、配置、资源基线和返回码。

正式 G04、回归、资源测量及未运行项以 [0066](../work_log/0066_qt_e16_qualification.md)
和冻结 qualification.json 为准。没有 Widgets、QML、Quick、GPU、合成、IME、滚轮、
动态模式、SMP、长期压力或完整 POSIX 资格。10ms 时钟的零差值是低于计时粒度，
不是零延迟；采样页面高水位不是绝对峰值。静态分发/重链接/逐成员许可审查未完成，
不发布新 Release。
