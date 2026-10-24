# Qt 移植讨论备忘

2026-10-24；用户已确认Qt为GUI主线、SDL为次选，阶段与验收以xos_plan.md v0.5
的E13–E20/G系列为准。本文保留技术缺口评估；未引入依赖、未开始移植，不改E08顺序。查阅时官方滚动文档标为Qt 6.12.0；这不是已为XOS选定的版本。
XOS不在[官方支持平台](https://doc.qt.io/qt-6/supported-platforms.html)中。

## 两条路线的差别

| 项目 | Qt Widgets | QML / Qt Quick |
|---|---|---|
| 首个建议目标 | 单窗口按钮、文字框、文件编辑/保存 | 先无界面QML对象/绑定，再一个软件渲染场景 |
| 图形路径 | QtGui/QPainter/raster backing store → 自定义QPA → 像素呈现 | 相同平台基底，另加QtDeclarative/QV4和Qt Quick场景图 |
| GPU是否必需 | 普通raster Widgets不必需；不包含QOpenGLWidget | 不必需，有官方software adaptation；GPU特效不属于这条路线 |
| 额外复杂度 | 字体、输入、焦点、布局、事件与重绘 | JS解释器/GC/导入模块/绑定与动画、场景图及渲染调度 |
| 建议顺序 | QtCore最小验证后先做 | Widgets基底稳定后独立试验，不能当作简单换皮 |

Widgets可通过QPainter/QBackingStore做CPU绘制，见
[QBackingStore](https://doc.qt.io/qt-6/qbackingstore.html)。
Qt Quick的[软件适配](https://doc.qt.io/qt-6/qtquick-visualcanvas-adaptations-software.html)
不支持ShaderEffect和粒子效果；变换文字与非整数缩放也有质量/更新效率限制。
因此不需要为了第一扇Qt窗口先移植OpenGL/Vulkan，但也不能承诺完整Quick效果兼容。

QML是语言/引擎，Qt Quick是可视场景图，两者分别验收。QV4可通过
`QV4_FORCE_INTERPRETER`禁用JIT，减少可执行内存和ISA代码生成的初期负担；
构建时是否能完全去掉JIT及相关分配器，仍需对固定源码版本做feature验证。
官方记载JS/GC专用栈通常分别约4MiB/2MiB，它们是独立内存区，不能误当作
C++调用栈大小。当前XOS的128KiB可用调用栈仍须另测递归/解析峰值。
见[JS引擎配置](https://doc.qt.io/qt-6/qtqml-javascript-finetuning.html)。
Qt Quick不依赖Qt Widgets；先做Widgets是降低首轮平台适配风险的建议，
不是模块依赖，也不排斥提前验证无界面QML引擎。

## 两者共同缺少的基底

以下是根据当前XOS源码和平台接口作出的工程判断，不是Qt官方替XOS给出的清单。

1. C++工具链和ABI：Qt 6要求[C++17编译器](https://doc.qt.io/qt-6/cmake-get-started.html)。
   E08-3只搬binutils，尚无XOS原生G++/libstdc++。先验证构造/析构、静态初始化、
   原子操作及目标C++运行库；异常/RTTI是否裁剪按所选Qt与应用测试决定，不能
   武断认定所有功能都必须开启，也不能拿内核受限C++选项直接编整个Qt。
2. 时间、等待与线程：QtCore事件循环需要单调计时、定时器、可睡眠且可唤醒的
   事件分发。当前yield轮询和受限pipe不能直接充当Qt事件系统。标准多线程路线
   还需共享地址空间线程、锁/条件等待、TLS与退出清理；单线程feature裁剪可先
   调研编译，尚未证明足够。Quick在许多平台使用独立渲染线程，软件后端也不能
   自动证明整个模块可无线程，见[场景图线程说明](https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html)。
3. 图形/输入：目前是VGA文本和串口，没有像素显示面、键鼠事件、焦点或窗口生命周期
   ABI。先建窄呈现/输入机制及用户态服务，再交给Qt适配；不要将Qt类或SDL对象放内核。
   Qt本身不以UEFI为前提；显示来源由XOS引导/平台层处理，不让QPA直接调用固件。
4. Qt平台移植：CMake交叉配置、OS识别/平台定义、QtCore文件/时钟/事件后端；
   QtGui的QPA integration/screen/window/backing-store/input；字体数据库、字体
   栅格化与文本排版、图片插件和资源路径。剪贴板、输入法、网络、多窗口和原生对话框
   可分期，未支持的能力明确禁用。按实际配置补系统调用，不先宣布必须实现完整POSIX。
5. 内存/文件：动态堆和真实fd是起点；仍需验证Qt采用的虚拟内存/映射回退、对齐分配、
   大对象与字体/像素缓冲峰值。当前每任务256MiB、全局512MiB、每会话8个打开文件
   都要用实际Qt样本评估。不能由一个8MiB malloc探针推断Qt可运行。
   当前文件路径仅ASCII；Qt的Unicode文件名映射需另适配，首个演示可明确限制路径。
6. 构建工具：第一轮可在宿主运行同版本moc/rcc/uic等生成器，交叉构建目标Qt；
   在XOS内原生构建Qt及其应用工具套件，是另一层验收，不必阻塞第一扇窗口。

## SDL兼容的作用

Qt为主线，SDL为次选，取代此前SDL兼容优先方向。优先让Qt QPA对接XOS窄服务，
像素呈现、输入队列、计时和等待可被SDL适配复用；SDL不是Qt的必需中间层。
SDL版本/子集按另一GUI库的实际需要另行确定，不阻塞Qt阶段。

Qt官方[QPA插件清单](https://doc.qt.io/qt-6/qpa.html)没有现成SDL插件。
SDL兼容不会自动提供Qt事件分发、字体、QPA或QML引擎；使用SDL路线仍需维护
自定义QPA和事件循环集成。QPA不保证跨版本源码/二进制兼容，必须固定Qt版本。
此处是基于接口清单的判断，不宣称第三方世界不存在SDL-QPA项目。

## 建议讨论的验收顺序

- QtCore无界面：字符串/文件/定时器/事件投递，等待可唤醒、退出资源回收。
- 单个全屏raster窗口：稳定重绘、字体、键鼠输入，再接按钮/文本框与保存。
- Qt Widgets小编辑器：输入/选择/布局/保存/重启，记录内存与响应；不提前造桌面。
- 无界面QML绑定/JS/GC，再Qt Quick软件窗口；明确不支持的效果，记录帧时与内存。
- 必要线程能力随实际模块提前补齐；GPU后端、多窗口/剪贴板/输入法/网络及更完整应用生态另作后续目标。

上述能力已拆入计划E13–E20，各阶段按依赖推进；QML不依赖Widgets。线程需求须在
E13核对，不能统一推迟。具体版本/feature配置仍待实施时冻结，不增加E08前置项。

## 许可证准备

Qt按所选版本/模块核对LGPL/GPL/商业及第三方条款，不能整体改成XOS的Apache。
无动态链接器时，静态Qt/静态插件的对应源码、补丁、重链接对象/配方、运行替换后
程序与安装说明都应提前准备。具体发布方案依模块和适用许可复核；当前没有Qt分发。
参考[Qt官方开源许可义务](https://www.qt.io/development/open-source-lgpl-obligations)。
