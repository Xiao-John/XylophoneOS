# 0066 E16 QtGui / XOS QPA 受限功能资格

2026-10-28。**G04: PASSED（受限功能）；静态分发资格: NOT_RUN。**
真实 Qt 6.8.3 QtGui、静态 xos QPA 和图形应用已在 XOS/QEMU 内运行。
不是宿主 Qt 窗口、自研显示 Demo 更名或编译通过替代运行。
冻结输入、逐组结果、截图、串口、失败及命令见
[qualification.json](../reports/qt_e16_qualified_20261028/qualification.json)。

## Git、范围与产物

启动时 main=`244ac40`，PR #8 HEAD=`d1e108d`、开放、非 Draft、无 review；
独立 worktree `XylophoneOS-qt6-e16`、分支 `codex/qt6-e16-qpa` 从该 HEAD 开发。
工作中 PR #8 获批准并 squash merge 到 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`。
`git diff d1e108d origin/main` 为空：上游合并树与实际 E15 HEAD 一致。
E16 独立实现提交已重放到该 main，当前实现提交 `adc7142`；差异不重带 E15。
没有改内核、Display Service、公共 ABI、线程 SDK 实现、E15 QtCore 端口或其他 worktree。

QtBase 锁定 v6.8.3 / `c07c2d5a527a644d36e7853d55132ae38921682f`，官方源码 archive
SHA-256 `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`。
原 E15 七补丁和受限事件分发器保持原样；E16 有独立 prepare/configure/build 入口及
0008 平台补丁。完整私有源码重新提取/重放后递归逐文件比较无差异。

| 实际产物 | SHA-256 |
|---|---|
| E15 libQt6Core.a（应用实际链接） | `d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3` |
| libQt6Gui.a，18,301,106 bytes | `af459dcccc314a45f943b354d906cac80c03f9e3bc45ac5f3e4369f37b622270` |
| qt_demo.elf，20,962,376 bytes | `cd63910fdebea9b6dd1c83dff1876ee237c4c5ebe7fdab49bf23f878e454d352` |
| XOS xos.img，buildef83c9fc92217380 | `7ae8e55e3ef9223c67c94075523696b8e12c48fe304e9da7954a4681b7bbd87f` |

应用位置 `build/qt_e16/delivery_app/qt_demo.elf`；Gui 在 `build/qt_e16/gui/lib/`，
插件在 `delivery_app/libQXosIntegrationPlugin.a`，系统在 `qualified_system/`。
[构建回执](../reports/qt_e16_qualified_20261028/qt_demo.receipt.json) 保存实际编译链接命令。
QtGui/Core 及所选 Qt 依赖的归档未定义符号对实际 SDK/Qt 定义求差，最终只剩链接器
`_GLOBAL_OFFSET_TABLE_`；实际 ELF 的 `nm -u` 为空，使用 `--no-undefined` 链接。
不把未被应用使用的整个 SDK API 或所有 QtGui API 认作已验收。

## G04 客体证据

四套正式夹具共17组，均 PASSED；每个 Gate 附同一套源码/补丁/SDK/QtCore/QtGui/
字体/ELF/镜像/QEMU/配置与夹具 SHA-256。580项系统源码输入、66项SDK源码输入和
全部SDK artifacts复核相符。G04各目录的原始串口、QEMU命令、返回码和资源基线均保留。

| 面 | 真实验证与限制 |
|---|---|
| 图形/文字 | QGuiApplication 静态 xos 插件初始化；QWindow/QBackingStore/QPainter 图形、线条、Qt 字体匹配、FreeType/HarfBuzz 文字；QTimer局部刷新 |
| 像素/边界 | 客体 QFile 导出真实 QImage；QEMU 物理显存与 scanout；800×600/stride3200、1,920,000字节逐字节一致；整帧及超边界 QRegion 裁剪后的两个角刷新 |
| 输入 | QMP真实PS/2英文、Shift/Ctrl/Alt、press/release、鼠标位置及点击/释放；Qt主线程收到事件；隐藏/重新显示的Qt焦点事件 |
| 溢出 | 暂停真实输入消费者后注入80组按键；64项FIFO真实溢出，resync/lost≥65、释放held P键、序列严格递增，后续英文输入恢复 |
| 等待/退出 | 正常两个线程；诊断采样线程观察GUI和输入均blocked（waiting=2/threads=3）；disconnect取消输入等待，pthread_join后线程/内核栈回1/1 |
| 生命周期 | 同进程三次窗口创建/销毁；客户端fault/kill、服务kill、服务处理真实present时fault；服务重启后新Qt客户端恢复；第二独占窗口-16诊断退出 |
| 资源不足/救援 | 32,000×32,000 QImage真实分配失败返回null；4线程配额已满时输入线程创建真实失败；无VGA时-19明确失败；每例串口Xshell可继续操作 |

截图见 [scanout](../reports/qt_e16_qualified_20261028/g04_pixels/scanout.png) 和
[交互后](../reports/qt_e16_qualified_20261028/g04_interactive/interactive.png)。
宿主仅注入硬件事件/读取扫描输出，不写 framebuffer 或调用客体事件处理函数。
独占 Surface/IPC 无独立数值统计API；通过后续独占connect、整进程页/任务/完成记录
精确基线、同进程线程/栈和现有G02生命周期测试验证本范围回收，不虚构计数器。

## 测量和回归

正式主验收采样最高3,723用户页（15,249,408 bytes，含一次诊断采样线程）；相同ELF
先前补验最高4,128页（16,908,288 bytes，见attempts/qualified_lifecycle）。
这是绘制后的采样高水位，非绝对峰值；libc可保留释放后的堆页直到进程退出。
单进程仍最多65,536页、4线程；正常GUI两个线程，默认worker栈256KiB。

正式主验收的present时钟差值为0或10ms，绘制加present为0–60ms；相同ELF补验曾
记录110ms。普通输入的8次按下样本从客体PS/2时间戳到Qt事件处理器为0–30ms。
时钟粒度10ms，零差值仅表示低于计时粒度；溢出探针的故意1.8秒暂停不计普通延迟。
QEMU为11.1.2、pc-i440fx-10.0、TCG、qemu64,+rdrand、单核512MiB；宿主曾并发运行
独立测试VM，这些是本次功能测试中的观察值，不是稳定吞吐、vsync或实时上限承诺。
CPU百分比、绝对峰值、其他显示模式/stride运行、真机、SMP和长期随机压力 NOT_RUN。

有服务时进程资源基线为 `[130278,3,1]`（free pages/tasks/completions）；客户端结束
回此基线。服务停止并收集完成记录后回 `[130322,2,0]`。无VGA基线为 `[130323,2,0]`。
重复窗口各次线程/栈均从1/1返回1/1。故障进程由已有机制一次回收，无新内核特例。

同一新镜像重跑：G02 syscall65/66 19组；T0/T1 15组；pthread10组；C++线程10组；
文件8组、持久化4组。冻结E15 QtCore/SDK上的12组客体回归全部通过，涵盖smoke、
wait/wake、posted/nested/timer、quota、fault、文件错误/重启读回、C++/TLS/异常、
内存采样、互斥竞争、interrupt和timer teardown。没有重跑未受影响的完整Dash、
原生GCC或CPython大套件；没有借用旧镜像结果声称新组合全量验收。

## 原始失败和修复

- FreeType Unix后端缺sys/mman.h：改选上游标准C缓冲后端，未造mmap。
- moc include路径及QRect/QRegion夹具编译错误：修复；曾因编译失败误用旧ELF运行pixel
  探针，超时失败保留，验收入口随后加入回执全部输入校验，防止旧产物被当成新代码。
- QThread::wait曾先于底层detached线程/栈回收：真实pixel检查退出74，未放宽判据；
  仅QPA输入改成现有SDK joinable pthread并join，QtCore不改。后续正式和补验通过。
- HarfBuzz subset归档有两项缺失定义：0008补入原有graph/gsubgpos-context.cc；闭包
  通过。该补充未改变应用ELF字节，仍按新依赖回执重跑四套G04。
- C++回归首次缺threading_legacy.elf，补齐原冻结输入重跑通过。文件/持久化客体本已
  通过，汇总器误读报告文件名；原失败汇总保留，corrected_report.json按真实报告更正。

## 已支持与未支持

支持一个独占全屏raster窗口、RGB32用户RAM、Qt文字/基础英文输入、三键鼠标、
局部重绘、posted events/定时器、可取消输入等待、窗口销毁和新客户端服务重启恢复。
Screen按API读实际mode，但只验上述QEMU模式。隐藏窗口丢弃GUI输入，独占Surface
直到销毁才撤销。第二窗口为明确失败并终止该客户端，非可恢复多窗口API。

Widgets/QML/Quick、GPU/合成、窗口管理、IME/复杂布局/滚轮/USB、动态插件、
通用poll/select、同客户端服务重连、完整QtGui API、Qt端原生重建均不在本次资格内。
实现与复现配方见 [E16实施](../plans/qt_e16_execution.md)。

QtBase/PCRE2/zlib及新增FreeType/HarfBuzz/DejaVu/MD4C、raster/region原许可与来源
保留；license-audit材料检查通过，不代表逐成员、完整静态重链接/对应源码、安全或
再分发审查完成。**不发布新Release，不授予Qt静态发行资格。**
