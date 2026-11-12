最终基线已补审至 `4c9b6f8feb0667d7169167e406da662be789876c`。以下保留早期阶段的验证计数与状态，尤其 e624 阶段的 IPC unsupported 描述已由上游 #114 更新；当前状态和增量结论以 `latest_upstream_review.md`、总报告及最终结果为准。

本附件合并分阶段审阅记录。阶段内计数不相加；最终覆盖与结果以 `repository_inventory.csv` 和 `validation_results.json` 为准。宿主绝对路径已机械替换为 `${XOS_ROOT}`、`${XOS_AUDIT_WORK}` 等占位符，以下不是未经处理的原始日志。临时清单名仅用于说明记录来源；本报告附有最终 CSV、结构化结果、关键日志与可重放命令。

# XOS UI / SSG / 端口构建审计分报告

审计者：`/root/audit_plans`。日期：2026-11-12。

仓库：`${XOS_ROOT}`。
初始审计基线是上游 `a676e21292fc322de0814aaaeee80819e41371ba`；收尾时根 agent 已快进至
`e6246faf8eefac305a99528f727b1592ee93a5b2`。本报告描述共享工作区当前改动，不代表已经发布或通过完整客体验收。

## 1. 覆盖范围及边界

逐文件完整阅读清单在 `../ui_audit_files.txt`，机器可读统计在 `../ui_audit_coverage.json`。
完整阅读 156 个文件、按收尾工作区计 16,465 行；这些是阅读量，不是运行时覆盖率或“已发现全部问题”的证明。

| 范围 | 完整阅读文件数 |
|---|---:|
| `src/user/ssg`、`src/user/interactium`、`src/user/apps`；Aurora Browser/Desktop、browser_http；Qt aurora/qpa/runtime/editor 的 C++ 与头文件 | 75 |
| `src/ports/**/*.py` | 15 |
| `scripts/*ssg*`、`scripts/modern_apps*.py`、`scripts/modern2_source_audit.py` | 25 |
| Qt 11 个 patch、Aurora Browser 1 个 patch | 12 |
| 工具链、配置、HTML/CSS、相关测试与文档等，详见清单 | 29 |

另外检索、交叉阅读了工作日志及计划。为避免把检索片段算作通读，没有将所有被引用的工作日志放进完整阅读计数。

本 agent 没有完整解包审计 Qt/litehtml 等上游压缩包，没有审计所有第三方源码；庞大的 `source_lock.json` 只检查了相关字段与来源关系，未逐项阅读所有哈希；没有视觉审计图片与全部 SVG。其他 agent 负责内核、libc、服务、程序及其余构建发行代码。不能将此分报告称为每个第三方源文件已经全部审完。

## 2. 本轮修复：9 项确定问题，11 个文件

### UI-1：焦点切换后自动重复按键重写了按键归属

位置：`src/user/interactium/service.cpp`、`service.hpp`；回归：`tests/interactium_model_test.cpp`；契约：`docs/contracts/interactium.md`。

复现顺序是窗口 A 接收首次按下，焦点切到 B，硬件自动重复发出相同 make code，再松键。旧 `note_key_press` 每次将归属重写为当前焦点，于是 A 永远收不到 release，B 收到没有对应首次按下的重复与 release。PS/2 实现确实会把重复 make code 作为 key_press，因此不是假设出的输入路径。

改为首次按下记录 owner，同一键后续重复沿用 owner，release 沿用同一 owner；release 后再次按下才按新焦点归属。返回 owner 后由现有队列路由，不新增另一套跟踪机制。

真实服务模型回归在修复前退出 134，失败于新添加的归属断言；修复后通过，ASan/UBSan 通过。该契约与仓库原有“release 返回首次按下窗口”的规则一致，避免只修 release 而重复仍改变 owner。

### UI-2：显示输入队列恢复事件只通知焦点窗口

位置同 UI-1。若 A 曾收到按下、随后切到 B，display 队列溢出丢失了 A 的 release，旧路由仅通知 B resync；A 的 QPA 保留过期的按键状态。

现在 display 级 resync 广播给所有活窗口，并清空路由器的按键归属；指针按钮状态只给当前命中/焦点的 pointer target，其余窗口收到 0。保留原始 lost 数。每窗口自身队列溢出的既有恢复路径仍由其原有逻辑处理。

真实模型测试在只修 UI-1 时仍退出 134，失败于旧窗口应收到 resync 的断言；本修复后通过。新增两块模型场景合计验证重复/松键归属和 resync 后重新归属。

### UI-3：Notes 在打开另一个路径前保存，写错了目标文件

位置：`src/ports/qt6/editor/main.cpp`。

确定的数据路径：打开 A，编辑 A，在路径框改成 B，点击 Open，再选 Save and continue。旧实现的 `saveFile()`总取路径框，先把 A 的内容写入 B，再打开被覆盖的 B。即使 B 原来有自己的内容，也会丢失。

改为 `saveFile(target)`。显式 Save/Ctrl+S 仍将路径框用作保存目标，保留既有 Save As 行为；Open 的确认分支保存到 `loadedPath` 后再打开路径框中的目标。文件标题依据实际成功保存的目标更新。尚未保存过的新文档没有 loadedPath，点击 Open 后的 Save and continue 会要求 Cancel 后先保存新文档，避免擅自把打开目标当保存目标。

此项为源码路径确认，**没有 Qt 编译、真实 GUI 或客体回归**。本环境没有可用 Qt6Widgets 与完整交叉工具链，报告不将其计入已运行测试。需要在具备真实 Qt 的环境执行上述 A/B 场景，并覆盖 Save As、保存失败继续保留缓冲、未命名文档及取消操作。

### UI-4：浏览器被拒绝的链接退化成当前页重载

位置：`src/ports/aurora_browser/view.hpp`；相关正常入口是 `src/ports/aurora_browser/main.cpp` 的导航与内容解析器。

旧 `on_anchor_click` 先调用 resolve。对不允许的 scheme 或越过允许目录的 URL，resolve 返回空字符串；把它交给顶层 navigate 后，后者按“有意输入空 URL”解析成当前页，导致原应拒绝的点击变成重载并添加历史。

现在日志仍输出 resolved target，但回调交给最终导航入口的是原始 href，使最终入口保留“拒绝 URL”与“有意空链接”的区别。未添加新的 URL 接受范围或网络功能。

此项也是**源码路径确认，未 Qt 编译/GUI/客体验证**。请以当前允许的本地相对链接、空链接、HTTPS 链接及目录越界链接做真实 Qt 回归。browser_http 独立解析器通过测试不能证明本 GUI 修复已验收。

### BUILD-1：可移植 receipt 后追加了绝对路径

位置：`src/ports/qt6/build_widgets_fixture.py`。

旧实现先 `portable(receipt, ..., strict=True)`，后追加 extra_source、moc_header、qrc 与 generated_sources 的哈希键，最终 --portable-receipt 仍泄露机器绝对路径且不可迁移。把输入追加移动到 portable 转换前。

宿主检查直接从真实脚本提取并执行原语句，使用真实文件进行 sha256；对照 HEAD 与工作区，4 个输入键从绝对路径变为 `${XOS_...}`。此为 receipt 序列化检查，未调用编译器或构建 Qt。

### BUILD-2：Windows 的 Ninja depfile workaround 在所有平台执行

位置：`src/ports/qt6/configure_widgets.py`。

注释所述问题是 Windows Ninja 无法解释 MSYS /c/...；旧代码无条件删除 depfile/deps 规则和 `.ninja_deps`，POSIX 构建因此也失去头文件依赖。仅增加 `if os.name == 'nt'` 条件，Windows 既有行为保留。

宿主检查执行真实条件块：POSIX 的两份 Ninja 内容与 `.ninja_deps` 保持不变；Windows 分支仍移除对应字段及依赖库。这是隔离文件重写回归，**没有 Qt configure / 完整增量构建验证**。

### BUILD-3：P1 缺失工具的错误诊断和 manifest 状态错误

位置：`scripts/build_ssg_p1.py`。

`Path(shutil.which(tool) or '')` 在工具缺失时把空字符串解析为仓库目录，然后读取目录导致 `IsADirectoryError`，没有说清缺哪个工具；异常路径仍把 manifest 留成 BUILDING。现在缺工具明确报 `FileNotFoundError('missing tool: ...')`，异常将状态写成 FAILED。

使用真实脚本、临时最小 sdk manifest 与 Qt cache、实际缺失的交叉编译器执行：修复前 returncode=1/status=BUILDING/IsADirectoryError；修复后 returncode=1/status=FAILED/缺少 x86_64-elf-g++。没有伪造成功编译。before/after JSON 留于 `../ui_audit/`，当前结果可通过 `verify_failure_paths.py` 重现。

### BUILD-4：历史 source 抓取器会覆盖已经冻结且扩展过的 lock

位置：`scripts/modern_apps_sources.py`。

固定目标是 `docs/reports/modern_apps_20261029/source_lock.json`。该历史抓取器重建的初始字典不能保留后来加入的其他依赖绑定，重复运行会覆盖冻结清单。入口发现现有 lock 便立即拒绝，并指向已有 `modern_apps_prepare.py` 恢复固定输入。

真实命令执行退出 1、报告清晰、在任何网络抓取之前返回；前后 lock sha256 一致：`7da8bcef7b9af46a7c4df0f94f907ca6db79b0de484c2495f9dc7280ab8ec980`。没有改冻结文件。

### BUILD-5：P4A 验证器有确定的局部变量作用域错误

位置：`scripts/run_ssg_p4a_validation.py`。

`main()` 中 `scenarios = list(scenarios)` 将 scenarios 变为局部变量，却在赋值前读取它；完成 preflight 后必然触发 UnboundLocalError。删除没有必要的复制，迭代既有全局 tuple。

检查真实源码编译出的字节码：修复前为 LOAD_FAST_CHECK/STORE_FAST，修复后为 LOAD_GLOBAL，且不再 STORE_FAST。**这是静态作用域检查，未运行完整 P4A 客体套件。**其旧镜像依赖另见第 5 节，不能因为这一行修好就宣称整套可在新构建上运行。

## 3. 验证结果与准确命令

全部命令从仓库根运行。临时产物放在 `../ui_audit`，没有写入历史冻结报告。

### 3.1 真实 C++ 实现宿主验证

```sh
g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc/shared/include tests/interactium_model_test.cpp src/user/interactium/service.cpp src/user/interactium/window_manager.cpp src/user/interactium/dispatcher.cpp -o ../ui_audit/interactium_model_after
ASAN_OPTIONS=detect_leaks=0 ../ui_audit/interactium_model_after

g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc/shared/include tests/interactium_transport_test.cpp src/user/interactium/service.cpp src/user/interactium/window_manager.cpp src/user/interactium/dispatcher.cpp src/user/interactium/service_loop.cpp -o ../ui_audit/interactium_transport_after
ASAN_OPTIONS=detect_leaks=0 ../ui_audit/interactium_transport_after

CXX=g++ ASAN_OPTIONS=detect_leaks=0 python3 tests/browser_http_test.py --output ../ui_audit/browser_http

g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -Wno-error=misleading-indentation -fsanitize=address,undefined -fno-omit-frame-pointer tests/aurora_blur_cases.cpp src/ports/qt6/aurora/blur.cpp -o ../ui_audit/aurora_blur
ASAN_OPTIONS=detect_leaks=0 ../ui_audit/aurora_blur
```

| 运行单位 | 结果 | 计数口径 |
|---|---|---|
| Interactium model | PASS / exit 0 | 1 套；含本轮新增 2 个已先复现的场景。原套件没有导出总 testcase 数，不虚报 |
| Interactium transport | PASS / exit 0 | 1 套既有协议/运输回归 |
| browser_http | PASSED | 208 checks + 4,096 malformed vectors；报告明确 network=NOT_RUN |
| Aurora blur | PASS | 396 exact-neighborhood vectors + 6 rejections |

ASan 与 UBSan 开启。默认运行时 LeakSanitizer 因当前环境 ptrace 条件退出，所以仅设置 `detect_leaks=0`；**没有声称做过泄漏检测**。browser_http 首次默认找 clang++ 失败，改用实际存在的 g++ 后通过。blur 首次 -Werror 被既有测试第 23 行 misleading-indentation 挡住，仅对这一既有 warning 降级；没有改业务代码或测试来掩盖运行失败。

### 3.2 Python 定向及语法验证

```sh
python3 ../ui_audit/verify_script_repairs.py
python3 ../ui_audit/verify_failure_paths.py
PYTHONPYCACHEPREFIX=${XOS_AUDIT_WORK}/ui_audit/pycache python3 -m py_compile scripts/build_ssg_p1.py scripts/modern_apps_sources.py scripts/run_ssg_p4a_validation.py src/ports/qt6/build_widgets_fixture.py src/ports/qt6/configure_widgets.py
git diff --check
```

上述均通过。`verify_script_repairs.py` 包含 receipt 前后对照、2 个依赖文件平台分支和 P4A 字节码检查；`verify_failure_paths.py` 包含 2 个真实失败入口。后者直接 subprocess 实际构建/抓取脚本，没有复制业务或 mock 编译器。前者只执行对应的实际 AST 语句，不等同于完整构建。

收尾时语法检查曾捕获本轮引入的 portable 行缩进错误，已立即修正，5 个改动 Python 文件全部重新通过 py_compile。不要引用修正前短暂状态作为最终代码。

这份分报告有 4 套 C++ 宿主运行、2 个 Python 定向检查命令以及语法/diff 检查。根 agent 的 17 组独立验证应另列并去重，不将两边套件数字简单相加为“独立案例总数”。

## 4. “找 bug 的测试题”查找结果

能确认存在多轮第三方 bug hunt/盲测，但本仓库没有原始完整题目。当前 `git ls-files blind_test CONTEST` 只返回 `blind_test/tools/pipe_drive.py`，它是运行程序、记录日志并从 FIFO 输入的驱动。`.gitignore` 明确忽略 `/CONTEST/` 和 `/blind_test/`。

仓库中能交付的原文是以下历史修复说明，它们可以证明原始材料的名称和内容主题，但不能冒充原始测试题：

| 已提交的文件 | 明确引用的原始输入 |
|---|---|
| `docs/work_log/0212_file_service_found_bug_fixes.md` | `CONTEST/bug-hutting-contest-3/found_bug.md`，15 项静态/宿主问题 |
| `docs/work_log/0213_second_bug_hunt_fixes.md` | `CONTEST/bug-hutting-contest-4/real_bugs.md`，3 项缺陷与 1 项注释问题 |
| `docs/work_log/0214_bundle_installer_hardening.md` | `CONTEST/bug-hutting-contest-1/found_bug.md`、`CONTEST/bug-hutting-contest-2/found_bug.md` |
| `docs/work_log/0215_s2_bug_hunt_fixes.md` | CONTEST 内 5 份 Season-2 报告 |
| `docs/work_log/0216_s3_contest_report_fixes.md` | contest-1/2/4 内 3 份 `found_bug_s3.md`，去重 11 项 |
| `docs/work_log/0223_s4_contest_report_fixes.md` | 桌面 `归档_副本.zip`，其中 6 份 `found_bug_s4*.md`；日志只记录简写 sha `a760b0f6…dc57` |

可将这些已提交文档原样给用户；要交付真实题目原文，还需取得其本地被忽略的 CONTEST/blind_test 目录或 `归档_副本.zip`。没有从修复记录反向编造题目、没有把省略的 sha 伪装成完整摘要。有关公开仓库历史/分支的额外查找由根 agent 汇总。

## 5. 未修项、限制与合理处置

### 5.1 本次审计直接观察但没有足够依据扩大修改的项

| 项目 | 当前依据/影响 | 未改原因与下一步 |
|---|---|---|
| QPA reply 目标容量 | `src/ports/qt6/qpa/qxos.cpp` 的 exchange 只判断 payload_length <=4096，再复制给调用者较小数组；理论上畸形 peer 可超出目标数组 | 未找到当前真实服务合法回复路径会越界。按用户限制不为推测的异常边界新增校验；若协议允许不可信 peer，先固定最小真实触发再做入口容量检查 |
| P4A 新旧构建形态 | `scripts/run_ssg_p4a_validation.py`、`scripts/export_ssg_p4a_report.py` 依赖旧 `xos.iso`/`xos.img` 与旧 manifest 键；当前新构建改用 install ISO | 保留历史验证/导出意义，不覆盖冻结报告。将来明确建立“当前主干”验证输出与镜像适配入口；本次只修可独立确认的作用域错误 |
| 派生 P4A SDK 的来源绑定 | `scripts/prepare_ssg_p4a_toolchain.py` 读取源 manifest，但部分复制输入未先逐项核对原摘要，而是在派生产物重算摘要 | 发现绑定不足，未复现当前合法输入被错配；需要匹配工具链输入和真实构建验证后再改，不能把通用猜测当作当前已发生 bug |
| Qt/GUI 真实验证 | Notes、browser 点击路径和完整 QPA 没有在本环境编译或运行 | 缺 Qt6Widgets、对应 SDK/host tools/cross compiler。必须在具备匹配依赖的环境构建并跑客体/真实 GUI；源代码确定的问题已修，不假称验收 |
| 浏览器网络能力 | 当前 UI 是受限本地内容浏览；`browser_http` 是独立解析准备 | 208+4096 的解析器测试不构成 DNS/TCP/HTTP/TLS/网络浏览验证，不把待开发功能包装成 bug 修复 |
| Aurora shell 应用条目 | shell 有 File/Settings/Browser/Trash 等外观入口，真实应用实现有限 | 当前范围/演示限制；真实进程注册、启动、失败显示与生命周期是后续完整功能，不凭空实现一组产品 |

### 5.2 仓库 TODO：先区分历史过期项与真实未完成项

以下是基线文档复核结果；根 agent 对其他范围的新改动可能进一步关闭其中具体子项。

| 条目 | 当前状态与证据 | 处置建议 |
|---|---|---|
| VM0–VM3 | 源码已有实现和 sys67；`docs/work_log/58b24599_vm3_lifecycle_sdk.md` 仍记录 implemented_unqualified / V1–V7 未全部资格化 | 更正旧“未实现”表述；下一步做完整匹配构建/客体资格，不重写同一实现 |
| COW | `docs/work_log/cow1_snapshot_progress.md` 已有真实父子隔离及部分失败回滚证据；普通 fork 仍 eager、COW 为 opt-in | 完成 COW-L1/L2 生命周期及所有 kernel write/pin 入口；COW2 多线程与 COW3 资格不能提前宣布完成 |
| IPC IP2/IP3 | `docs/work_log/8c39b047_ipc_ip3_notification_and_wait_set_abi_registrati.md` 有代码，SDK 为 registered_unsupported、运行 feature bits 仍 0 | 需要真实 guest 验证再宣称支持；不是“看到枚举就已可用” |
| AU1/AU2 | 音频已有实现与 S4 修复；tech_debt D9“仅文档”过期 | 校正文档并做真实端到端音频验收，不重复起一个假实现 |
| SL1/SL2 与 BT-01 | 创建权限继承和 nested dash 修复已存在，见 `0216_sl1_create_authority.md` / `0217_sl2_shell接入.md` | 不把历史 nested dash 问题再列为当前未修 |
| SL3/SL4 | `0218_sl3_diag_tools.md` 对真实 Make C 工程明确 not_run，缺 seed；SL4 env/cwd/FD/深链矩阵未完成 | 恢复 seed，跑真实工具链流程；不能将 wrapper 存在当 Make 工程已过 |
| DU4 | `0209_du4_p2_autinstall.md` 已有安装/自启实现 | state 的 DU3/DU4 未完成登记过期，不重复做 |
| 旧镜像 smoke | `0224_drop_legacy_images.md` 已迁移主体 smoke | 不把历史 smoke 断裂当整个当前仓库仍坏；具体 P4A 遗留入口单独挂账 |
| Qt 发布材料 | tech_debt D7/D10 已记录 2026-11-04 发布并收口 | state 的“发版中止”过期；新版源码变更仍需要新版构建/材料，不能反写旧冻结报告 |
| D4 Pillow | `_malloc_r` vector14 线程故障，公开记录为 BLOCKED | 真实 guest/线程堆分配复现与根因修复；本轮 UI 宿主测试不能替代 |
| FS-01/02/04/08 | 多打开 writer lock、目录替换、打开文件 unlink/rename、cwd 身份语义受限 | 架构级工作需确定 inode/句柄身份模型与迁移测试；根 agent 汇总文件服务已修子项 |
| FS-03 | ftruncate/full-disk 为短写注入验证 | 需要真实近满 FAT 镜像端到端测试、恢复门证据 |
| FS-05/07 | 路径逐段 stat 成本；FAT 非 sparse，扩大文件需零填充 | 前者无量化性能证据，不盲目优化；后者是存储模型成本，不能为速度去掉零填充语义 |
| Device A2 / A1 / N2 | grant table 与设备迁移尚未整体完成，网络进程化有依赖 | 按 authority 接口→设备迁移→网络依赖顺序规划，不在 UI 审计中越界实现 |
| D12 | 基线是 3 份归档来源脚本未共享 validator | 根 agent 本轮正在/已落实共享 archive_member_map；本 agent 不重复修改 |
| D13 / D14 | Studio 首跑间歇超时、consumer exit/Notes shutdown 根因仍未解决；旧 stress 23/24、P3C scoped 资格；globalAtomicSnapshot=NOT_IMPLEMENTED | 当前主干稳定复现并留资源/生命周期证据；不能把旧 23/24 改成通过或偷偷重写历史证据 |
| xypm P3 | 完整事务和签名仓库未开始 | 是后续开发项目，不能用本轮小修声称完成 |
| E10/E11 / SMP / QML | 系统客体重建/自举、SMP 资格、Qt Quick/QML 等未完成 | 按依赖阶段推进，分别定义门禁与失败标准 |
| BT-02–05 / 07–08 | usage、/bin 布局、CPython prefix、xos-diag 安装和源/发行差异 | 根 agent/userland agent 正在处理这些范围；最终以他们的实际 diff 和验证为准 |
| BT-06 | clock 为墙钟而非真实进程 CPU 计时 | ABI/产品限制，要引入 accounting 才能改变，不能仅改文案假称已修 |

Qt patches 的 MODIFICATIONS 文档原来只登记 10 个补丁，漏掉 0011；已通知根 agent，收尾时根 agent 已补上第 11 个补丁的源码登记。本 agent 没有改历史冻结许可报告，也不作法务结论。



---

# UI / Qt / SSG 测试补充审阅

日期：2026-11-12。审阅基线：`e6246faf8eefac305a99528f727b1592ee93a5b2` 及本次共享工作区修复。

## 1. 实际覆盖

补读清单：`ui_test_full_reads.txt`，共 **168 个文件、13,489 行、850,676 字节**。与分配的 `ui_test_read_queue.txt` 比较，无遗漏、无额外冒记、无重复。全部文件都完整阅读；没有把文件名检索或部分截取计为通读。长文件分段读至末尾，曾遇输出截断的批次已重新完整读取后入账。

本次从此前 `ui_audit_files.txt`、`root_audit_files.txt`、`kernel_ports_audit_files.txt`、`userland_audit_files.txt`、`kernel_audit_files.txt`、`final_coverage_additions.txt` 所列范围之外补读 GUI/SSG/Qt/Aurora/browser/modern 测试、对应 guest runner 与 fixture。额外协调接管 `display_*`、`interactium_*`、`virtio_gpu_*`、`vm3_qt_acceptance.py`、`mock_semantic_agent.py`、`semantic_pipe_guest.py` 及其 probe；`pillow_static` 留给 userland 审阅者。

| 文件类别 | 数量 |
|---|---:|
| Python runner、校验器与测试 | 99 |
| C++ fixture（`.cpp` / `.cc`） | 40 |
| C fixture | 1 |
| JavaScript / ES module fixture | 20 |
| HTML fixture | 4 |
| Swift OCR 工具 | 1 |
| patch / qrc / 文本 fixture | 3 |

原 UI 分报告完整阅读 156 文件与本次补读无重叠，合计 **324 个独立文件、29,954 行**。这只是本 agent 的阅读范围，不是整个仓库的运行覆盖率。按上述前缀及 fixture 目录复查，既有六份清单和本清单之外没有遗漏的相关测试文件；其余非 UI tests 由 userland 审阅者负责。

## 2. 本次补充修复：3 类、10 文件

### T-UI-1：可选 VirtIO 隔离子场景没有执行，却进入成功检查列表

文件：`tests/virtio_gpu_acceptance.py`。

实际流程仅在传入 `--access-payload` 时导入并运行 MMIO / PCI I/O 访问 probe，检查对应 fault vector；原末尾无条件把 `user_MMIO_and_PCI_IO_fault_isolation` 放入 `checks`。不传参数即产生错误的成功声明。

最小修复是在完整测试流程成功后，传入参数才追加该检查；未传参数则在报告 `not_run` 中记录 `user_MMIO_and_PCI_IO_fault_isolation: --access-payload not supplied`。两种后端任一可选子场景抛错，都到不了成功追加处。

验证：完整源流程检查及 Python 语法编译通过。没有模拟整台 Guest，没有执行客体隔离 probe，不能据此声称 MMIO / PCI I/O 客体验收通过。

### T-UI-2：4 个 Qt runner 复制启动镜像时丢失 ISO 后缀

文件：

- `tests/qt6_fault_probe.py`
- `tests/qt6_file_errors.py`
- `tests/qt6_persist_probe.py`
- `tests/qt6_sdk_probe.py`

四处都接受 `--image`，先复制成固定 `boot.img` 再交给 `tests/boot_smoke.py` 的 `Guest`。`Guest` 未显式给定 `iso` 时按传入路径后缀选择介质，因此合法 `.iso` 输入被转换成 floppy 命令，无法按 ISO 启动。

每处只把复制目标改为 `boot` 加原始 `a.image.suffix`，让现有统一入口判断继续生效。`.iso` / `.ISO` 保留 CD-ROM 语义，`.img` 及无后缀仍走原 floppy 语义。没有改变 disk 内容、QEMU 配置或实际客体断言。

宿主核验执行四份 runner 的真实路径赋值 AST、真实 `Guest.__init__` 中的介质选择语句，再调用真实 `run_qemu.qemu_command`。4 个 runner × 4 个后缀，**16 个当前用例通过**；另执行 HEAD 原始语句的 **16 个基线用例**，确认原 `.iso` / `.ISO` 共 8 例都错误选择 floppy。证据是 `ui_audit/verify_ui_media_selection.py` 与 `ui_audit/ui_media_selection.json`。

命令生成测试使用 `QEMU=/bin/true` 仅满足可执行文件路径解析；没有启动该命令、没有运行 QEMU、没有真实镜像启动，因此结论仅是启动命令介质选择正确。

### T-UI-3：5 个 SSG 派生 runner 记录了别的 runner 的源哈希

文件：

- `tests/ssg_p2g4_guest.py`
- `tests/ssg_p2g5_guest.py`
- `tests/ssg_p2g6_exhaust_guest.py`
- `tests/ssg_p2g6_navigation_guest.py`
- `tests/ssg_p2g6_reload_guest.py`

五个派生 runner 的 `report['inputs']` 都沿用 `ssg_browser_pages_probe.py` 名称并计算它的哈希，未记录实际执行 runner。这使新采集证据不能据此绑定实际脚本版本。

每处只将输入源列表首项改为 `Path(__file__).name`，仍经 `ROOT / 'tests' / name` 计算源文件路径及哈希，并保留 `ssg_browser_structure.py`。原始 `ssg_browser_pages_probe.py` 本来就记录自身，因此没有改它。没有改历史冻结报告、历史 SHA 或验收预期。

宿主核验实际执行报告输入 `for` 循环 AST，对照 HEAD 原始循环：**5 个当前 runner** 都记录准确的自身路径与当前 SHA-256、以及正确的 structure.py 路径/哈希；**5 个原始 runner** 都只记录 pages probe 而缺自身。证据：`ui_audit/verify_ui_runner_provenance.py`、`ui_audit/ui_runner_provenance.json`。这不是客体验收。

以上 10 个文件总 diff：14 行新增、11 行删除；无新测试文件、无新工具或流程进入仓库。

## 3. 运行命令与结论

以下命令工作目录为仓库根；`../ui_audit` 是此次审阅的中间证据目录。

```bash
QEMU=/bin/true PYTHONDONTWRITEBYTECODE=1 python3 ../ui_audit/verify_ui_media_selection.py
PYTHONDONTWRITEBYTECODE=1 python3 ../ui_audit/verify_ui_runner_provenance.py
PYTHONPYCACHEPREFIX="$PWD/../ui_audit/pycache" python3 -m py_compile tests/qt6_fault_probe.py tests/qt6_file_errors.py tests/qt6_persist_probe.py tests/qt6_sdk_probe.py tests/virtio_gpu_acceptance.py tests/ssg_p2g4_guest.py tests/ssg_p2g5_guest.py tests/ssg_p2g6_exhaust_guest.py tests/ssg_p2g6_navigation_guest.py tests/ssg_p2g6_reload_guest.py
git diff --check -- tests/qt6_fault_probe.py tests/qt6_file_errors.py tests/qt6_persist_probe.py tests/qt6_sdk_probe.py tests/virtio_gpu_acceptance.py tests/ssg_p2g4_guest.py tests/ssg_p2g5_guest.py tests/ssg_p2g6_exhaust_guest.py tests/ssg_p2g6_navigation_guest.py tests/ssg_p2g6_reload_guest.py
```

结果分别为 `PASSED_HOST_COMMAND_SELECTION`、`PASSED_HOST_PROVENANCE_SELECTION`、语法编译退出 0、diff 检查退出 0。原 UI 源码修复的真实模型回归与编译结果在 `ui_audit_report.md`；根 agent 独立执行的全部 host 套件应单列统计，不能把这里的源语句核验混为 guest 通过。

## 4. 尚未重新资格化的旧图形 runner

当前 `src/ports/qt6/qpa/qxos.cpp` 的 `interactium_connection::open()` 连接名字 `interactium`，`integration()` 在连接/hello 失败时明确退出，`createPlatformWindow()` 为每个窗口创建独立 Interactium window。以下 **31 个**图形 runner 在启动路径上只有 `display-start`、没有 `interactium-start`。它们保留了此前 Display Surface 代际的工作流；使用历史匹配二进制的历史结果不能自动转化成当前 QPA 的验收结果。

| 组 | 具体文件 |
|---|---|
| Aurora | `tests/aurora_browser_acceptance.py`；`tests/aurora_desktop_guest.py`；`tests/aurora_platform_guest.py`；`tests/aurora_standard_button_guest.py` |
| Qt GUI / Widgets | `tests/qt6_aurora_acceptance.py`；`tests/qt6_aurora_memory.py`；`tests/qt6_editor_errors.py`；`tests/qt6_gui_acceptance.py`；`tests/qt6_widgets_acceptance.py`；`tests/qt6_widgets_probe.py`；`tests/qt6_widgets_resources.py` |
| Browser paging / IPC | `tests/ssg_browser_pages_probe.py`；`tests/ssg_consumer_exit_stress.py`；`tests/ssg_ipc_guest.py`；`tests/ssg_p2g4_guest.py`；`tests/ssg_p2g5_guest.py`；`tests/ssg_p2g6_exhaust_guest.py`；`tests/ssg_p2g6_navigation_guest.py`；`tests/ssg_p2g6_reload_guest.py` |
| Notes range / edit | `tests/ssg_notes_live_edit_guest.py`；`tests/ssg_notes_live_no_log_guest.py`；`tests/ssg_range_boundaries_guest.py`；`tests/ssg_text_range_guest.py` |
| Multi source / watch | `tests/ssg_p3b_guest.py`；`tests/ssg_p3b_restart_guest.py`；`tests/ssg_p3b_stress_guest.py`；`tests/ssg_p4a_guest.py`；`tests/ssg_watch_guest.py`；`tests/ssg_watch_stress_guest.py` |
| VirtIO + Qt | `tests/virtio_gpu_acceptance.py`；`tests/virtio_gpu_fault_profiles.py` |

`tests/display_compat.py` 和 `tests/display_smoke.py` 仅测 Display 协议本身，不应因未启动 compositor 判作此问题，已排除。

还有两项具体代际矛盾：

- `qt6_gui_acceptance.py` 的 `second` 子场景期待 `exclusive Surface connect failed (-16)`；`tests/fixtures/qt6/gui_demo.cpp` 的 `second` 在 800 ms 后创建第二窗口，但没有定时关闭。当前 QPA 支持独立多窗口，因此仅加 compositor 后这个旧场景也不会按原预期退出；`virtio_gpu_acceptance.py` 同样运行 `second` 并等待退出。需改成真正验证两窗口可用、独立回收的当前场景，不能只删除失败字符串断言。
- `tests/aurora_browser_no_display.py`（无 display 启动，故不在上表）、`qt6_gui_acceptance.py`、`qt6_widgets_acceptance.py`、`virtio_gpu_fault_profiles.py` 保留 `unavailable or invalid Display Service mode (-19)` 旧错误文本。当前 QPA 失败入口为 `Interactium connect/hello failed`，不能继续按旧文本标为当前无设备验收。

完成条件：用当前源码与同一 SDK/receipt 重建 Qt GUI、Notes、Browser、相应 fixture 和系统镜像；按现有 `tests/vm3_qt_acceptance.py` / `tests/interactium_aurora_guest.py` 的 compositor 启动路径更新需要迁移的 runner，并正确回收 display/compositor；对输入、多窗口、service death、无设备场景重新定义实际预期；在固定 QEMU 与真实 guest 中运行并保存新目录证据。本环境缺 Qt SDK、交叉工具链和 QEMU，未作这些客体迁移，也未静默放宽旧断言。

## 5. 证据解读边界

- `ssg_browser_structure_test.py`、`ssg_p2g4_ab_validator_test.py`、`ssg_watch_events_test.py` 是真实 Python 校验器面对合成记录的宿主回归；这些测试本身已明确其不是客体完整性证明。本次没有修改其数据或把它们宣传为真实 provider 缺陷。
- SSG 验证器多处绑定 Browser 代码与 receipt。初始审计已修改 Browser `view.hpp`，因此当前源码不能直接通过旧 frozen receipt 的重放源哈希检查；需保留历史 checkout 或重建新证据，不能覆写旧 SHA。
- `tests/ssg_watch_incomplete_verify.py` 消费旧单行 `P3C_EVENT {...}`；当前 `src/user/ssg/watch_service.hpp` 输出分帧 `P3C_EVENT_BEGIN/PART/END`。`scripts/replay_ssg_p3c_evidence.py` 明确将它用于 `prior-stress-partial` 的旧记录，因此保留历史入口，而非盲改旧证据解析。当前事件回归走 `ssg_watch_events.py` 与对应新 verifier。
- 未执行 guest runner、Qt fixture 编译、Swift OCR 或截图视觉验收；没有安装额外工具。已读不等于已跑，host 通过不等于 VM3 / Aurora / SSG 当前客体资格化完成。

## 6. 找 bug 题目交付

已经单独完成 `docs/reports/comprehensive_audit_20261112/bug_hunt_questions.md`，24 道依现存工作日志与真实回归重建的题目索引，另附一个被历史复核否定的 IPC 泄漏说法。它明确声明不是原题全文；准确记录原 `CONTEST` / `blind_test` 忽略目录、原报告名与缺失原因。此前逐项检查 56 条相对文件链接存在，公开证据路径检查结果 `PUBLIC_READY`。本次测试补读没有改动题目、历史报告或测试 fixture。


---

# 非 UI 测试收尾补读

本轮只读 `userland_tests_delegated_to_ui.txt` 指定的 35 个文件；逐个阅读了完整内容，没有以文件名扫描代替阅读。独立全读清单为 `ui_assist_test_full_reads.txt`，共 **35 个唯一文件、3,715 行、195,565 字节**（本轮修复后统计）。与交接清单相比，缺失、额外项、重复项均为 0。不要把这 35 项计入 userland 已交付的 271 项清单。

## 修改：2 类测试问题，1 个文件

修改文件：`xos/tests/e08_post5_p1.py`。这两项是测试运行器及报告问题，不是新增两项 OS 运行时缺陷。

### 1. 非正循环次数使 R1 空跑仍报成功

原入口允许 `--levels r1 --cycles 0` 或负数。后续 `range(a.cycles)` 不执行任何 R1 编译、链接、运行，仍追加 `R1 0 cycles`，并进入统一的 `report['status'] = 'passed'`。正常 preflight 和启动即使成功，也不能证明 R1 实际运行。

修复在 `parse_args()` 后一次性校验 `a.cycles >= 1`。非法参数通过现有 `argparse` 错误通道退出，退出码为 2；没有新增内部重复校验或任意上界。

### 2. 实际源码大小被固定写成 1 MiB

原 R3 使用 12,000 个短函数生成 `big.c`。实际生成 **385,814 字节**，原成功检查固定声称 `R3 1MiB source/8MiB BSS/64 includes`。

修复将源码部分改为读取实际 `big.c` 的字节数。当前表述为 `R3 385814 byte source/8MiB BSS/64 includes`。压力源内容、函数数量、BSS 和 include 数量均保持原值，没有为了匹配旧标签增加压力负载。

## 验证证据

在仓库根执行以下命令，均通过：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 ../ui_audit/verify_e08_post5_contract.py
PYTHONPYCACHEPREFIX="$PWD/../ui_audit/pycache" python3 -m py_compile tests/e08_post5_p1.py ../ui_audit/verify_e08_post5_contract.py
git diff --check -- tests/e08_post5_p1.py
```

辅助验证直接抽取并执行真实运行器的 AST 节点，没有复制参数校验或源文件生成逻辑，也没有模拟整个 Guest：

- 参数解析及入口校验：HEAD 原版和修复版各执行 5 组，共 **10 组**，覆盖省略 `--cycles`、`-1`、`0`、`1`、`10`。原版全部接受；修复版仅拒绝 `-1`、`0`，退出码 2。
- 源码生成和检查文本：执行两版本真实生成表达式及真实报告表达式，确认生成内容完全相同，实际 385,814 字节；修复后报告与文件长度一致。
- 验证原始结果：`ui_audit/e08_post5_contract.json`；可复现脚本：`ui_audit/verify_e08_post5_contract.py`。

**没有运行客体 GCC 压力测试、启动 QEMU 或执行 R1/R2/R3/R5 的客体编译。** 上述结果只证明参数入口、实际生成输入、报告文本、Python 语法和补丁格式符合修复目标；不构成客体编译成功的证明。其余 34 个补读文件本轮仅做完整源码阅读，没有重复运行已由根代理负责的宿主回归。

## 阅读范围

| 分组 | 文件数 | 核对内容 |
| --- | ---: | --- |
| bundle 验证与 ISO bundle daily / P2 install / reject | 6 | 数据摘要、预存包冲突、安装阶段、正负结果标记、镜像与种子选择 |
| E08 integration / storage / post5 | 3 | preflight、源码及 sysroot 来源、编译命令、失败判定、资源恢复、持久化 |
| FB0 运行器及 fixture | 6 | 客户端错误、服务异常退出、实际客户端接口注入、文件摘要 |
| FB12 运行器及 fixture | 5 | 异常/取消 fixture、故障包写入器错误路径、回归范围 |
| fake xypm | 1 | marker 身份测试的替身边界 |
| Pillow 静态核心及诊断 | 4 | 真正静态 `_imaging`、PNG/BMP 数据、线程诊断与资格结果分离 |
| SL1 authority fixture | 1 | set/clear、子孙创建、无效 mode，以及未覆盖的真正提权拒绝场景 |
| kernel / speaker lease / persistence | 3 | 当前共享修改后的页表检查、租约源码及 tick 模型、重启后文件验证 |
| SQLite VFS fixture | 1 | 当前共享修改后的规范路径、文件身份别名锁、cwd 变化后 journal |
| Xshell 行编辑及 UI | 2 | 光标、UTF-8、转义序列、PATH 选择、诊断与资源恢复 |
| XYPm JSON / profile | 3 | 实际解析器边界、配置路径提示与特性错误分类 |

## 已核对且未修改的边界

1. `iso_bundle_daily.py`、`iso_bundle_p2_install.py`、`iso_bundle_reject.py` 没有本轮另一代理修复的“把终端输入 echo 当作输出成功”的同类路径。daily 等待安装消息及 `ls` 的 daily/idna 项；P2 等待 maintenance 和包信息输出；reject 等待 digest mismatch / not found / not executable，并排除安装成功消息。它们的输入文本本身不包含对应的成功或失败标记。没有修改这三个文件，也没有启动镜像来验证它们。

2. `fixtures/shell_launch/sl1_authority.cpp` 的 T4 注释已经承认，实际只验证 mode 99 返回无效参数；它不能证明一个没有 `can_create` 的调用者无法设置创建权限。T5 主要证明父进程能创建，虽然调用 `wait`，但没有核对返回值和子进程退出状态。记录为现有测试覆盖边界；未把它们等同于已复现的内核权限漏洞，也未扩展 fixture。

3. `pc_speaker_lease_check.py` 编译真实租约声明，核对源文件中的处理次序，并用 tick 模型解释旧租约失败与当前安全启动延迟范围。它的模型结论不能代替真实调度和硬件的音频验收。

4. `pillow_static_guest.py` 明确把单线程核心资格与线程诊断分开，`PASSED_CORE_SUBSET` 不代表完整 Python、LocalPilot 或依赖链资格通过。fixtures 的静态核心和压缩炸弹测试有真实数据断言，但本次没有对应客体运行环境。

5. `fake_xypm.c` 是 marker 身份验证的专用替身；FB0 与 FB12 错误 fixture 是对真实客户端或写入器实施故障注入。读取这些 fixture 不意味着验证了真正包安装事务、IPC 内核或所有客体异常路径。

6. `kernel_smoke.py`、`sqlite_vfs_paths_test.c` 仅阅读了共享工作区中的现有修改，没有再编辑。userland 正在修改的另外六个 ISO runner 不在本轮范围，也未触碰。没有修改冻结历史报告、缓存产物或生成文件。

本轮源文件变更至此冻结。剩余客体验证和已明确记录的覆盖缺口交根代理统一列入最终报告。
