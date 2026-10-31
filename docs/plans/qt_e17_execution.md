# E17 / G05 提案：Qt Widgets 6.8.3 与真实图形文本编辑器

> **状态：PROPOSED / NOT_STARTED / G05 NOT_RUN。** 本文件仅提交下一阶段的范围、技术风险与验收计划；未修改 Qt/内核/SDK 实现，未编译 Widgets、未运行 G05。请维护者 review 后再将实现作为独立功能 PR 交付。
>
> **本提案起点：** upstream `Xiao-John/XylophoneOS` `main@c39cef1f365bf5944b7dce920c304ae396cbb49b`（2026-10-29 查询时）。开工时须重新读取最新 `main`、PR、工作区占用与 ABI。
>
> **建议工作分支：** `codex/qt6-e17-widgets`；本提案分支为 `codex/qt6-e17-plan-20261029`，两者不混用。

## 1. 当前已经具备的东西

- E14/G02：QEMU BIOS VBE XRGB8888、PS/2 输入、受保护 Display Service，`sys_display=65`、`sys_display_present=66`。
- E15/G01/G03：QtBase **6.8.3**、静态 QtCore、受限 XOS 事件分发器、线程/计时/文件/资源的真实 guest 功能资格；PR #8 已合并。
- E16/G04：真实 QtGui、静态 XOS QPA、`QWindow/QBackingStore/QPainter`、FreeType/HarfBuzz 字体、单独占全屏 Surface、键鼠与区域刷新，17 个 G04 测试组受限通过；PR #9 已合并。
- PR #10 的 Xshell 文字编辑/文档、PR #11 的 xypm P2 事务与恢复已合并；`main` 还整合了日常工具、UTF-8 文件名及 ncursesw 前期工作。**这些新组合没有自动继承旧冻结 Qt G04 的整体客体资格。**
- Qt Widgets、QML/QV4、Qt Quick、完整发行成员许可与静态重链接审查、绝对峰值/长期压力都**没有通过**。正式 Release 仍为 `v0.0.1-1026`。

## 2. 建议下一功能：E17/G05，不与 E18 混在一起

目标是**在真实 XOS/QEMU 客体中运行 Qt 6.8.3 Widgets 构建的可用全屏文本编辑器**。这要比改名 E14 gfxdemo 或只有 `QPushButton` 更进一步：实际打开、输入、选择、修改、保存、sync、重启读回文件。

首轮建议的实际 Qt 组件：

- `QApplication`、`QWidget`、`QPlainTextEdit`、`QLabel`、`QPushButton`（如适用）、布局和状态/错误条；
- 一个**顶层全屏 QWidget**，所有编辑控件为同窗口子控件，不依赖第二个 native `QWindow`；
- 先用固定受支持目录的完整路径与内置简单路径输入，不要求原生文件对话框、菜单弹窗、IME 或多窗口；
- 英文 PS/2 键盘输入、退格、方向键、Shift 选择、Ctrl+S 保存和鼠标光标/选择；如实际 Qt Widgets 行为与原始按键映射不兼容，必须有可复现修复和按键级客体测试；
- UTF-8 **文件内容字节保真**、换行结尾/无结尾、空文件；文件名编码按最新 libc/files 能力实测，首轮可限制已验证路径，不因为 U2 已有探针就宣称全部 Unicode 文件路径可用。

## 3. E17 的真实技术风险与优先顺序

### W0：固定构建输入并复用 E15/E16

固定 QtBase v6.8.3 `c07c2d5a527a644d36e7853d55132ae38921682f`、官方源码及补丁的实际哈希；独立 `prepare_widgets_source.py`/`configure_widgets.py`/`build_widgets_fixture.py` 或同等可复现入口，启用实际 `FEATURE_widgets`。必须用 XOS GCC/SDK 编译目标 QtWidgets 静态库，并实际链接到 XOS ELF。

E15/E16 的静态库仅在哈希、SDK 和 ABI 一致时复用；上游最新 `main` 引入了 libc/文件等改动，需要重新构建或做有依据的兼容检查。不得把旧 G03/G04 报告机械改绑新镜像。

### W1：Qt Widgets 子控件与 QPA 正确性

当前 `src/ports/qt6/qpa/qxos.cpp` 只准许**一个独占全屏顶层 window**，`backing_store::flush` 对非零 offset 或不同 window 明确拒绝。QPlainTextEdit 内部有 viewport/滚动区域，不能假设 Widgets 自然就能通过。

先做真实最小 `QApplication` + 单顶层 `QWidget` + `QPlainTextEdit` 的 XOS 客体绘制/键鼠探针；确认渲染通过 Qt Widgets 正式路径到顶层 backing store。若 Qt 6.8.3 的 `QWidgetRepaintManager` 实际调用要求 offset/裁剪扩展，先给出局部矩形和多子控件下的最小失败复现，再**只扩展用户态 QPA 的可证明语义**，不可暗改 Display Service 或申请 Qt 专属 syscall。拒绝额外 native 顶层、popup/对话框的路径应可诊断，不得静默黑屏。

### W2：交互与文本行为

验证鼠标点击定位、焦点、文本输入/删除、方向键、Shift+方向选择、滚动、多行渲染、中文 UTF-8 内容从文件载入后的显示及保存保真（不把中文输入法算作已支持）。测试 CR/LF、长行、文件尾换行、重复快速输入与 PS/2 resync 后避免卡键。首版不实现系统剪贴板；相关快捷键若不支持必须清楚标明或禁用，不伪装为可用。

### W3：安全保存的真实边界

**先审查当前 QFile/QSaveFile、新 libc/files 的 close/flush/sync/rename/replace/临时文件语义。** QtCore 的当前受限 profile 并不自动拥有 POSIX 原子覆盖/无覆盖重命名；xypm P2 的 journal 也不能自动给任意 Qt 文本保存提供事务保证。

保存策略必须在真实 API 可实现的范围内，优先验证“临时写入→完整检查/同步→合法替换或可恢复提交”，并核对目标已存在、覆盖失败、rename 失败及崩溃时旧文件的行为。对于无法保证的场景，保留原文件或明确 BLOCKED/UNSUPPORTED，不能先截断旧文件再假报失败安全。不得宣称突然断电/扇区撕裂安全，除非专项实测。

### W4：性能、退出与故障

持续占用最多一个全屏 Surface；QPA 的输入线程、Qt 事件循环与 Widgets 对象生命周期按已验证次序清理。测试进程/服务 fault、无显示设备、OOM/线程配额、反复打开/关闭，退出后串口仍可用、资源回基线。记录用户页采样、帧时/输入延迟及受限 512MiB QEMU/单核条件，不推导绝对峰值。

## 4. G05 最小验收矩阵（全部需要真实 guest 证据）

1. **Qt 身份**：真实目标 `libQt6Widgets.a`、与 QtGui/QtCore 和 SDK 的链接收据；QApplication/QWidget/QPlainTextEdit 在客体启动。宿主 moc/rcc/uic 不能冒充目标执行。
2. **绘图**：按钮/标签/编辑区的真实 QtWidgets 层绘制、字体、滚动、裁剪、局部重绘；QEMU scanout、客体像素/状态证据。
3. **输入/编辑**：真实 QMP PS/2 字符、退格、方向键、选择、鼠标光标与焦点、快捷键保存；未保存提示及退出。
4. **文件**：空/小/长文本、尾换行和 UTF-8 内容保真；打开→编辑→保存→sync→重启读取逐字节一致，失败不误报保存成功。
5. **失败保护**：只读、满盘、缺失、损坏/部分写入、失败关闭/同步、非法路径、进程被杀及恢复；**原文件不损坏**作为可证明目标，不满足则 G05 不通过或明确缩小资格范围。
6. **回收与旧功能**：三轮以上打开/关闭、fault、Display Service 死亡/重启、无 VGA、内存/线程配额，相关 G01/G03/G04/G02/线程/文件/持久化回归。对于最新 `main` 整合后较旧的冻结报告，须另行重验或界定差异。
7. **证据**：Qt tag/archive/patch、有效 feature、SDK、系统镜像、ELF、工具链、字体、源文件、夹具与证据包 SHA256，QEMU 命令、原始串口、截图、资源前后计数和未运行项。
8. **许可证**：记录 QtWidgets 实际启用的 Qt/依赖/字体条款；本地功能资格与静态分发/relink 审查分开，不发布新 Release。

## 5. 分支、责任与交付约定

- 本提案只修改 `docs/plans/qt_e17_execution.md`，不包含实现或 ABI 改动；**规划 PR 与 E17 实现 PR 分开**，符合用户要求的先沟通再干活。
- 后续实现建议在维护者确认占用后，从最新上游 `main` 开 `codex/qt6-e17-widgets`，只碰 Qt port、构建、Widgets demo、专用 tests、相关新工作记录和经协调的文档。
- 维护者/其他 Agent 已在做 ncursesw/nano、xypm 和日常工具，**不进入这些模块、通用文件服务、Qt 之外 libc 或内核**，确有必要时提交具体失败探针并协调职责。
- 新 syscall 要先在 `docs/contracts/abi_registry.md` 按原规则认领并通过审查；不要绕过现有 `sys65/66` 或使用未分配段。
- 不改旧 Release、历史冻结报告、用户日常盘、LocalPilot、代理与远程连接；独立 worktree、私有 build、真实作者归属和一功能一 PR。不直接 push 上游 `main`。
- 实现后的状态与结果区分 `PASSED`、`FAILED`、`BLOCKED`、`NOT_RUN`；未过 G05 不能以 Widgets 库可编译或一个按钮窗口替代功能资格。

## 6. 请维护者确认

1. E17 Widgets / G05 是否已经有人在本机或未公开分支开工？如果有，请给出分支、负责人、当前已修改的文件与冻结测试。
2. 是否同意以 **“Qt 6.8.3 Widgets + 单窗口文本编辑器 + 安全保存与 G05 客体验收”** 为下一独立功能 PR？
3. 若发现 Widgets 需要 QPA child-offset/viewport 修补，是否同意在 E17 只做**用户态 QPA** 的受限修正、保留 E16 旧消费者回归？
4. 关于现有文件覆盖/rename 语义，是否有其他人正在设计通用事务机制？请避免并行改底层，本线先提交真实消费者探针。
5. Qt 的静态发行许可专项由谁负责？本 E17 默认只做**未发行的受限本地功能资格**，除非另行明确完整审计边界。

> 这是一份**先发 PR 的计划提案**，不是 Qt Widgets 已实现声明；待明确责任后按此独立实施与验收。
