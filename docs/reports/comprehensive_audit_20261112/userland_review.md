本附件合并分阶段审阅记录。阶段内计数不相加；最终覆盖与结果以 `repository_inventory.csv` 和 `validation_results.json` 为准。宿主绝对路径已机械替换为 `${XOS_ROOT}`、`${XOS_AUDIT_WORK}` 等占位符，以下不是未经处理的原始日志。临时清单名仅用于说明记录来源；本报告附有最终 CSV、结构化结果、关键日志与可重放命令。

# XOS 用户态核心、程序与构建脚本审计报告

日期：2026-11-12。仓库：`${XOS_ROOT}`。审计基线：`a676e21292fc322de0814aaaeee80819e41371ba`。工作分支：`codex/comprehensive-audit-20261112`。

本报告是并行审计中用户态组的交付，供总报告合并。本阶段没有改写冻结验收证据。以下记录保存了本阶段修复过程；最终提交状态见总报告。

## 1. 范围与结论

逐文件读完 `src/user/libc`、`threading`、`services`、`loader`、`sdk`、`include`、`arch`、`drivers`、`programs`、`demo` 下的全部 92 个文件。`threading` 实际为 6 个文件，包含 pthread 实现、newlib 锁、头文件和编译入口；`demo` 为 6 个汇编程序。生成的 Unicode 区间表只读了内容及边界使用，没有手工修改。

另读完指定的 11 个构建脚本，以及作为关联调用方阅读的 `scripts/build_xypm.py`，共 12 个脚本。精确清单在同目录 `userland_audit_files.txt`；与磁盘目录枚举比较，运行时范围漏读数为 0。人工阅读覆盖不能证明项目不存在其他缺陷。

第一阶段本组修复 15 项具体行为问题，生产代码涉及 9 个文件，共 `+52/-22` 行。另扩充 2 个已有测试文件、新增 6 个测试文件。累计定向验证 85 个 case 全过，其中包含已有回归；这不是 85 个新缺陷。最后一处 execvp 修复后重新运行了 startup 15 + execvp 6 case。裸 `diag` 的 guest 回归、真实终端重启的 guest 回归，以及两个实验 SDK 的完整重建未执行，不能称为端到端验收通过。后续测试代码补审的独立结果、修改和边界见第 7 节。

## 2. 修复、触发条件与证据

### UL-01：失败的稀疏写错误改变逻辑文件偏移

文件：`src/user/services/files.cpp`，`undo_failed_write`。

触发：先 seek 到 EOF 之后，例如 1024，再写入；填零或实际写入遇到空间不足/磁盘失败。旧实现回滚时把逻辑偏移裁剪到原 EOF。应用下一次 `SEEK_CUR` 得到与失败前不同的偏移，重试位置也变了。

修复只改 1 行：物理 FatFs 游标仍安全恢复到原文件范围内，逻辑 `description->position` 恢复为写前偏移，避免回滚本身扩展文件。

证据：真实 `files.cpp` + FatFs 夹具中，既有 case 13/17 新增偏移断言。修前失败标签为 `gap failure preserves logical offset`；修后文件语义 24 case 通过。

### UL-02：无关 rename 删除正在使用的替换暂存文件

文件：`src/user/services/files.cpp`，`finish_recovery` 与 rename 分支。

触发：某客户端已经 `replace_begin`，暂存文件 XOSTMP.TMP 保持打开；另一项不涉及该目标的 rename 覆盖已有目标。旧 rename 完成清理调用公共恢复函数，顺手尝试删除仍被打开的暂存文件。FatFs 返回 FR_LOCKED，服务进入 `recovery_failed`，后续操作失效。

修复：公共清理函数增加一个默认启用的 `remove_staging` 参数；rename 明确不清理替换操作拥有的暂存文件。约 6 行改动，不增加新的日志协议或并发状态机。

证据：新增 case 22，在活跃替换期间完成无关 rename，再继续提交替换；旧版失败 `unrelated rename with active staging`，新版通过。原恢复故障夹具 21 case 也全部通过。

### UL-03：replace_chunk 部分写失败未记账，重试会重复写入

文件：`src/user/services/files.cpp`，`op::replace_chunk`。

触发：FatFs `f_write` 写入一部分数据后返回错误，且 `written > 0`。旧实现错误分支提前退出，`staging_written` 仍为旧值。客户端可重新提交相同 offset，服务接受后把前缀再次追加。

修复：先累计 FatFs 实际写入量，再选择响应状态；响应中的进度也反映真实累计值。约 4 行改动。

证据：新增 case 23，注入写入 2 字节后 FR_DISK_ERR，拒绝 offset 0 重试，允许 offset 2 补齐，最终文件严格为 `abcd`。修前失败 `reject duplicate staging prefix after partial error`，修后通过。

### UL-04：replace_abort 清理失败却返回成功

文件：`src/user/services/files.cpp`，`op::replace_abort`。

触发：abort 的暂存删除或清理失败，`abort_staging` 已标记服务恢复失败，旧调用方仍固定返回 `status::ok`。

修复 1 行，根据 `recovery_failed` 返回 `status::io`。

证据：新增 case 24，注入 unlink 失败；旧版失败 `abort reports failed cleanup`，新版返回错误并通过。

### UL-05：libc 启动重定向关闭了自己刚打开的标准描述符

文件：`src/user/libc/newlib_syscalls.cpp`，`xos_libc_init`。

触发：stdin/stdout/stderr 某槽位在 startup 中关闭，随后通过 open_paths 为它重定向。open 按最低可用编号分配，可能直接返回目标编号。旧代码仍按“移动不同描述符”的分支关闭目标，实际关闭了刚打开的文件，再把槽位置空。

修复 2 行：`opened == fd` 时保持已完成的重定向，跳过移动逻辑。

证据：新增 `tests/libc_startup_host.py` 与 `.cpp`，编译真实 newlib_syscalls、file_client、terminal_client，只在 syscall/IPC 边界设置夹具。覆盖 5 组关闭位图 × 3 个重定向目标共 15 case，检查 F_GETFD、真实读写调用路径和 close 恰好一次。旧版失败 `redirected descriptor remains open`，新版 `LIBC_STARTUP_CASES_PASSED=15`。

测试用 GNU nm/objcopy 重命名被测对象导出的 C 符号，避免替换宿主 libc；它是 Linux/GNU 工具环境的宿主测试，不是 guest 证据。

### UL-06：音频服务成功启动被显示为失败

文件：`src/user/programs/supervisor.cpp`，`ensure_audio_service`。

触发：服务尚未启动，spawn 成功返回正 PID。`audio start/restart` 的调用方以 0 判断成功，旧函数却返回 PID，导致“已实际启动但显示失败”。

修复 1 行：失败保留负错误码，成功统一返回 0；服务 PID 仍正常保存在原状态中。

证据：`tests/supervisor_host_test.cpp` 包含真实 supervisor 实现，覆盖新启动、已有运行实例、spawn 失败、退避、强制重启、发布失败。旧版新启动/重启成功断言失败，新版通过；与 UL-07 合计 9 个场景。

### UL-07：type 遗漏两个已实现的内建命令

文件：`src/user/programs/supervisor.cpp`，`builtin_named`。

触发：执行 `type display-start` 或 `type interactium-start`，旧列表不包含这两个真实 builtin。

修复 1 行，加入已有命令名；没有新增命令。

证据：同一 supervisor 宿主测试，旧版这两项为 false，新版为 true，并继续验证普通外部名不是 builtin。

### UL-08：xypm ensure --sha256 与自己的帮助文本不一致

文件：`src/user/programs/xypm.cpp`，命令行分派。

触发：按帮助使用 `xypm ensure <package> --sha256 <digest>`。旧 argc 5 分支仅接收 install/upgrade，ensure 被判作不支持的参数。

修复 1 行，ensure 复用原交易实现和 hash 校验入口。

证据：编译真实 CLI，仅让 syscall 边界拒绝 maintenance lease。修前 ensure 返回 2（不支持命令），修后与 install/upgrade 一样进入交易前置条件并返回 3（需要 maintenance write lease）；不支持的 remove + --sha256 仍返回 2。这仅验证参数分派，未执行实际包安装或完整 hash 验收。

### UL-09：完成 BT-02 的裸 diag 帮助行为

文件：`src/user/programs/supervisor.cpp`；测试 `tests/shell_launch_sl3.py`。

触发：裸输入 `diag`。旧条件带 `argc >= 2`，因此落入外部程序搜索并报告 not found，与仓库 BT-02 待办不符。

修复约 2 行：始终先识别 builtin，缺程序参数时打印 `Usage: diag <program> [args]`。

已在原 SL3 guest 脚本中加入断言：有 usage、无 not found、未启动 loader。相关 Python 语法通过，真实 supervisor 宿主代码仍编译通过。**本组没有运行 SL3 guest 测试，不把这一项写成已获得 guest 证据。**

### UL-10：Interactium demo 对服务死亡无限循环、空闲忙轮询并吞掉绘制失败

文件：`src/user/programs/interactium_demo.cpp`。

触发：display 输入持续返回 unavailable 等永久错误；旧循环把所有非零都直接 continue，无法返回。输入为空时也没有等事件；运行中 redraw 失败则退出循环却最终返回 0。

修复约 17 行增删：只有 display_again 使用已有 `wait_input`；等待/输入/重绘错误退出并返回非零，正常 Q/Escape 仍成功退出，沿用原释放路径。

证据：新增 `tests/interactium_demo_host_test.cpp`，调用真实 demo、Interactor service 和 window_manager，只设置 display syscall 边界。4 场景为永久输入错误、空闲后 Q、wait 错误、redraw 错误；夹具为旧无限循环设确定次数上界，避免测试本身挂死。旧版 4 项均失败，新版 `INTERACTIUM_DEMO_CASES_PASSED=4`，并检查只断开一次。

### UL-11：编辑器终端死亡后再也不能恢复输入

文件：`src/user/services/file_ui.cpp`。

触发：内建 edit 的输入期间，已移交 COM1 的 terminal 服务死亡。console hook 把桥接状态标为 unavailable，之后 read 固定返回状态错误；旧 editor_read_line 将它与空闲读一样永久 yield/continue，外层 shell 的恢复路径永远得不到运行机会。

修复 `+10/-1`：在确定桥接需要恢复时调用已有 `shell_terminal::recover`；恢复成功才丢弃未完成的当前输入行，保留文档 buffer 与 dirty，并返回原编辑命令循环。重启后提示 buffer retained；随后 :wq 可以保存并退出。没有把 false 改成退出编辑器，也没有清掉已编辑内容。

证据：新增 `tests/file_ui_terminal_host_test.cpp`，调用真实 file_ui 和 text。3 场景：追加过已完成行后在下个输入途中死亡；`:r` 替换输入途中死亡；`:i` 插入输入途中死亡且前两次恢复尚未就绪。旧版均进入无尽读循环；新版保存的文档分别是已完成追加内容、原文、原文，未完成输入不混入文档，3/3 通过。

边界：此修复使用现有 recover 契约，必须旧服务可回收且 COM1 可重新获得。它没有新增“杀死仍存活但卡住的终端”的 watchdog，也没有离线持久化未保存 buffer。真实 UART/guest 重启未执行，不能用宿主边界测试声称整个终端恢复链已经通过实机验收。

### UL-12：UTF-8 SDK candidate 没有导出 sys/mman.h

文件：`scripts/build_utf8_sdk_candidate.py`。

触发：使用该脚本导出的独立 SDK 编译引用 XOS mmap 接口的应用。旧脚本仅覆盖根目录 `*.h` 和 `xos/*.hpp`，遗漏 `src/user/include/sys`。仓库配套 newlib include 不提供这个 XOS 头；SDK 自身构建另加源码 include 路径，所以内部编译不能暴露导出缺失。

修复 1 行，按现有 threading SDK 做法拷贝 `sys` 子目录。

已验证脚本语法与头文件所在路径。**没有完成需要实验 newlib receipt/prefix 的整个 SDK 重建。**

### UL-13：threading SDK 的合法多层日志目录不能创建

文件：`scripts/build_threading_sdk.py`。

触发：`--logs-dir` 指向 build 内一个尚不存在的多层目录，路径校验允许它，随后 `mkdir(exist_ok=True)` 却因父目录缺失失败。

修复 1 行，使用与输出目录一致的 `parents=True`。脚本语法通过；未执行整个 threading SDK/C++ runtime 构建。这是标准 pathlib 行为导致的入口错误，没有额外引入路径规则。

### UL-14：newlib 下载/解压失败污染缓存，后续重跑永久跳过获取

文件：`scripts/build_newlib.sh`。

触发：旧脚本先创建 SRC，再 curl/tar；下载或解压失败后 SRC 仍存在，第二次根据目录存在判断跳过获取，随后 configure not found，退出 127。已有空缓存目录也触发同样问题。

修复 `+8/-3`：按 configure 文件判断完整源目录；先下载，解压到专用暂存目录，成功才替换 SRC。失败的暂存目录下次重新提取；旧空 SRC 也可恢复。未改冻结版本、下载来源、编译开关或依赖流程。

证据：新增 `tests/build_newlib_cache_test.py`，运行真实 shell 脚本，curl/make 在外部工具边界使用最小夹具，tar 为真实解压。下载失败重试、解压失败重试、旧空 SRC 修复 3 项，旧版重试全部失败 127，新版全部通过；每项还验证完整缓存下一次不重复下载。`sh -n` 通过。没有联网下载和构建完整 newlib。

### UL-15：execvp 重复添加尾斜杠，拒绝合法的 255 字符候选路径

文件：`src/user/libc/newlib_syscalls.cpp`，`execvp`。

触发：PATH 分量为 `/` + 252 个 `a` + `/`（共 254 字符），要查找的文件名为 `x`。拼出的目标本应是合法的 255 字符路径。旧实现只要 PATH 分量非空，就在长度检查及拼接时再加一个 `/`，因此在尝试打开文件之前返回 ENAMETOOLONG。相同目录去掉末尾 `/` 却能正常查找。后续再追加 `:/bin` 时，还会跳过第一个本来合法的候选，并在后者 ENOENT 后保留错误的 ENAMETOOLONG。

修复 `+3/-2`：分量不为空且最后一个字符不是 `/` 时才计入并追加分隔符，与 posix_spawnp 已有规则一致，没有修改 PATH 搜索策略、错误优先级或目录解析规则。

证据：扩展原 libc 宿主测试，链接真实 newlib_syscalls、loader、ELF、TLS、file_client 与 text；执行真实 `execvp → execve → 路径解析 → loader → file_client`，在原有 syscall/文件服务边界记录实际 open 路径并返回 not_found。6 场景覆盖普通尾斜杠、255 字符不带尾斜杠、255 字符带尾斜杠、真正 256 字符过长、空 PATH 分量、边界分量后接第二个搜索目录。旧版第 3/6 场景分别只调用 open 0/1 次并报 ENAMETOOLONG；修后分别调用 1/2 次并保留正确 ENOENT，6/6 通过。原 startup 15 case 同时重新通过。

命令仍为 `python3 tests/libc_startup_host.py`，新增输出 `LIBC_EXECVP_CASES_PASSED=6`。该测试证明路径构造和实际文件查询链，不执行成功的 guest 映像替换。

## 3. 可重复运行命令

以下从仓库根运行，手动 C++ 输出在 `build/comprehensive_audit_userland`，Python 驱动使用独立临时目录。原 79 case 在收尾时重新执行并全部通过；最后扩充的 libc 路径测试另与 startup 15 case 一起重新编译运行。

### 三个新增 C++ 宿主测试

```sh
mkdir -p build/comprehensive_audit_userland

c++ -std=c++17 -O1 -ffunction-sections -fdata-sections \
  -Isrc/user/include -Isrc/shared/include \
  tests/supervisor_host_test.cpp -Wl,--gc-sections \
  -o build/comprehensive_audit_userland/supervisor_host
build/comprehensive_audit_userland/supervisor_host

c++ -std=c++17 -O1 -Isrc/user/include -Isrc/shared/include \
  tests/interactium_demo_host_test.cpp \
  src/user/interactium/service.cpp src/user/interactium/window_manager.cpp \
  -o build/comprehensive_audit_userland/interactium_demo_host
build/comprehensive_audit_userland/interactium_demo_host

c++ -std=c++17 -O1 -ffunction-sections -fdata-sections \
  -Isrc/user/include -Isrc/shared/include \
  tests/file_ui_terminal_host_test.cpp src/user/sdk/text.cpp \
  -Wl,--gc-sections -o build/comprehensive_audit_userland/file_ui_terminal_host
build/comprehensive_audit_userland/file_ui_terminal_host
```

期望分别输出 `SUPERVISOR_CASES_PASSED=9`、`INTERACTIUM_DEMO_CASES_PASSED=4`、`FILE_UI_TERMINAL_CASES_PASSED=3`。

### libc、新 lib 构建缓存与真实 FatFs 回归

```sh
python3 tests/libc_startup_host.py
python3 tests/build_newlib_cache_test.py
sh -n scripts/build_newlib.sh

python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from make_work_disk import make_image
Path('build/comprehensive_audit_userland/private.img').write_bytes(make_image())
PY

c++ -std=c++17 -O1 -w -Isrc/third_party/fatfs \
  -Isrc/user/include -Isrc/shared/include \
  tests/fixtures/file_semantics/file_semantics.cpp \
  src/third_party/fatfs/ff.c src/user/services/fatfs_unicode.cpp \
  -o build/comprehensive_audit_userland/file_semantics
build/comprehensive_audit_userland/file_semantics build/comprehensive_audit_userland/private.img

c++ -std=c++17 -O1 -w -Isrc/third_party/fatfs \
  -Isrc/user/include -Isrc/shared/include \
  tests/fixtures/recovery/recovery_faults.cpp \
  src/third_party/fatfs/ff.c src/user/services/fatfs_unicode.cpp \
  -o build/comprehensive_audit_userland/recovery_faults
build/comprehensive_audit_userland/recovery_faults build/comprehensive_audit_userland/private.img
```

结果：libc startup 15 + execvp 6、newlib 缓存 3、file_semantics 24、recovery_faults 21。FatFs 测试读取私有 16 MiB 镜像，不改变用户工作盘。另有 14 个相关 Python 文件 `compile(..., 'exec')` 通过；本组修改的已跟踪文件 `git diff --check` 无错误。

### xypm 参数分派的局部证据

当时使用的临时文件（不随报告保留）为 `build/comprehensive_audit_userland/xypm_cli_stubs.cpp`、`xypm_profile.hpp`。构建命令：

```sh
c++ -std=c++17 -O1 -Isrc/user/include -Isrc/shared/include \
  -Ibuild/comprehensive_audit_userland src/user/programs/xypm.cpp \
  src/user/sdk/file_client.cpp src/user/sdk/text.cpp \
  build/comprehensive_audit_userland/xypm_cli_stubs.cpp \
  -o build/comprehensive_audit_userland/xypm_cli
```

该临时边界让 syscall 返回 `process_error_denied`，并把 `xypm_recover_run` 设为 3，仅验证命令进入已有交易门禁。它不是安装成功测试，不作为新的永久测试套件发布。

## 4. 未闭合的验证与真实限制

1. `tests/shell_launch_sl3.py` 新增裸 diag 断言尚未在 guest 执行；需要可构建、可启动的 SDK/guest 环境，不能把语法检查视为运行证据。
2. 编辑器终端恢复宿主测试覆盖 buffer 与循环语义，没有执行旧终端 PID 回收、COM1 恢复授权、实际 terminal.elf 再启动的完整链。恢复依赖已有桥接服务的契约；旧进程仍活着并永久挂起时，不保证自行脱困。
3. Interactium demo 宿主测试证明输入错误、等待和退出值控制流；真实显示设备和输入事件调度仍需 guest smoke。
4. UTF-8/threading SDK 的源码导出和目录创建已修，完整候选产物、archive provenance、guest probes 必须使用对应 newlib prefix/receipt 与冻结工具链另行生成和运行，不能改写既有验收状态。
5. newlib 缓存测试没有真正联网下载或编译 newlib；它验证的是失败重试与缓存发布流程，无法证明上游归档可用性或新 lib 的运行时质量。
6. xypm ensure 的修复只验证命令分派，实际维护租约、安装事务与 digest 校验仍由项目原有集成测试负责。

没有为了猜测的竞态或安全边界加入锁、重试协议、权限设计或新的工具流程。未把仓库已登记的 FatFs 单写描述符、有限 fork/pthread 支持、目录替换限制等再次计作本次新发现。

execvp 的尾斜杠边界候选在根代理追加授权后完成了实际链路复现、最小修复与回归，见 UL-15，不再列为待验证候选。

## 5. 给其他审计组的交叉核对

SQLite VFS 需要识别路径别名时，已核对并告知内核组：libc `fill_stat` 输出固定 `st_dev = 1`，`st_ino` 来源于文件服务响应 reserved；files 按 FatFs 目录项 `(sector, offset)` 分配非零 inode，成功打开同一目录项的 LFN/SFN/大小写别名得到同一标识，打开期间不可删除/改名替换，标识不复用。分配耗尽会失败，不降级成 0。

同时明确提醒：当前 FS-01 禁止已有可写打开情况下再打开同一文件；宿主 SQLite 别名锁复现不能直接等同于现有 guest 上的多个可写连接数据损坏证据。内核组负责自己的 VFS 改动与结论。

## 6. 本组修改清单

生产文件：

- `src/user/services/files.cpp`
- `src/user/services/file_ui.cpp`
- `src/user/libc/newlib_syscalls.cpp`
- `src/user/programs/supervisor.cpp`
- `src/user/programs/interactium_demo.cpp`
- `src/user/programs/xypm.cpp`
- `scripts/build_utf8_sdk_candidate.py`
- `scripts/build_threading_sdk.py`
- `scripts/build_newlib.sh`

扩充已有测试：

- `tests/fixtures/file_semantics/file_semantics.cpp`
- `tests/shell_launch_sl3.py`

新增测试：

- `tests/libc_startup_host.py`
- `tests/libc_startup_host_test.cpp`
- `tests/supervisor_host_test.cpp`
- `tests/interactium_demo_host_test.cpp`
- `tests/file_ui_terminal_host_test.cpp`
- `tests/build_newlib_cache_test.py`

没有修改其他代理拥有的 Interactium 内核模型、Qt、CPython VFS 或根代理的构建/发布脚本。宿主 demo 测试会编译当前共享工作区中的 Interactium service/window_manager，因此最终统一验证应以整个合并工作树为准。

## 7. 后续测试代码补审交付

根代理后续要求补读全仓 tests 剩余代码。本组独立全文读完 271 个测试/夹具，精确路径在 `userland_test_full_reads.txt`；收尾其余 35 文件 / 3,713 行由 UI 组接管读完，独立写于 `ui_assist_test_full_reads.txt`。本组运行时/脚本清单已清理成 104 行纯路径，不含说明文字，便于全仓去重。两个阶段都没有把“文件列出或搜索到”当作全文阅读。

详细报告是同目录 `userland_test_review.md`，含全部复现命令。源码现已冻结，待根代理统一最终验证。补审修复仅涉及测试流程或参考模型：

| 编号 | 修正 | 证据范围 |
| --- | --- | --- |
| T-UL-01 | SL3 Make 的宿主脚本导入提前到 Guest 启动前，消除实际同时写同一镜像的流程 | 源码/语法与调用顺序核对；未复现磁盘损坏、未跑 guest |
| T-UL-02 | binutils stress 的预期非零退出不再接受 0 | 真实嵌套函数 AST，新增 3 unittest 全过，旧版其中 1 项失败 |
| T-UL-03 | 6 个 runner 的 7 处 echo 标记等待独立结果行 | 实际 expected 常量 + 真实 Guest.expect 的输入回显边界 |
| T-UL-04 | pipe atomic fixture 的第三参 deadline 断言与现 ABI 对齐 | 1 处 -2 改为 0，C 语法检查；未跑 guest |
| T-UL-05 | device ABI runner finally 关闭 Guest | 1 行清理，源码/语法核对 |
| T-UL-06 | 2 个 ISO runner 查询真实 hello.elf，1 处 stat 检查真实 size 输出 | 与 T-UL-03 合计 10 个标记：修前假输出全接受，修后假输出全拒绝、真输出全接受 |
| M01 | IPC 参考模型排队请求保留 caller badge | 实际模型新用例旧失败，19 项模型 unittest 全过；不是内核验证 |

补审涉及 13 个已有测试文件，新增 `tests/binutils_stress_exit_test.py` 1 个文件；永久新增 unittest 合计 4 项（binutils 3、IPC 1）。13 个相关 Python 源码语法检查和相关 `git diff --check` 均通过。第一阶段 85 case、第二阶段测试判定器验证、参考模型 19 项保持分开报告；没有把这些合并成“全系统 guest 已通过”。

目前本组没有留下已确认但未修改的具体源码 bug。尚未完成的是第 4 节列出的完整 SDK/客体验收，以及测试报告明确列出的模型覆盖边界；这些验证限制仍然有效。Kernel 组后续对同一 FatFs 夹具增加的 O_TRUNC 回归由该组独立计数，不纳入本报告原来的 24 case 证据。


---

# XOS 非 UI 测试代码补充审阅

日期：2026-11-12。仓库 `${XOS_ROOT}`。

本组补读已完成，源码已经冻结。真正读完的 271 个文件逐项记在 `userland_test_full_reads.txt`，不包含他组代读项。收尾移交的 35 文件 / 3,713 行记在 `userland_tests_delegated_to_ui.txt`，由 UI 组独立读完并记录于 `ui_assist_test_full_reads.txt`、`ui_assist_test_review.md`。与根代理、UI 代理分工后的全仓范围以各自最终清单去重为准。本轮没有执行新的 guest，也未改写冻结验收报告。

## 已修正的测试流程

### T-UL-01：SL3 Make 在 guest 使用镜像期间又从宿主写同一镜像

`tests/shell_launch_sl3_make.py` 原本在启动 Guest 并完成两条 guest 命令之后，才通过宿主 `transfer` 导入 `/out/run_make.sh`。宿主工具与已挂载的 guest 各自维护 FatFs 状态，这个实际同盘写流程不应出现在测试中。

经根代理确认，已把原有 3 行脚本创建/导入移到 Guest 构造之前；脚本内容、后续命令与断言全部保持原样。没有引入并发框架或 mock。验证为完整源码审阅、Python 语法检查和调用顺序确认；**未运行 guest，也不宣称已复现磁盘损坏**。

### T-UL-02：binutils stress 的预期失败用例接受退出码 0

`tests/binutils_stress.py` 的实际嵌套 `run` 函数只在 `code is not None` 时比较退出码。S3 负例均传 `code=None`；其中截断 ELF 用例也没有额外 `contains` 断言，因此错误地成功退出的 linker 可以被记为通过。

已按同仓 `binutils_smoke.py` 的既有语义最小修改 2 行：None 表示必须非零，显式退出码继续精确匹配。新增 `tests/binutils_stress_exit_test.py`，从真实脚本 AST 提取并执行原函数，只在 guest 输出/资源读取边界提供数据，不复制判定逻辑。基线 3 个 unittest 中 `test_negative_case_rejects_zero` 失败；修后零退出拒绝、1/2/-1 接受、显式 42 精确比较均通过，3/3 PASS。

命令：`python3 tests/binutils_stress_exit_test.py`。这证明测试判定器已修，**没有执行真正 guest ld，也不代替 S3 guest 验收**。

### T-UL-03：七处 dash echo 检查把输入回显当成命令输出

`tests/dash_preinstall_smoke.py` 原来在发送 `echo PREINSTALLED_DASH` 后等待任意位置的 `PREINSTALLED_DASH`。终端回显的输入行已经包含这个字串，故没有真正结果也能通过。

先在该脚本最小修改 1 行，等待前后换行包围的独立结果行。随后完整阅读发现同一问题还存在于 `utf8_dash_smoke.py`、`iso_capacity_smoke.py`、`iso_dash_install.py`、`iso_bundle_install.py`、`iso_bundle_reboot.py`；最后一个含 first/second boot 两个标记。合计 6 个文件、7 个 expected 常量，各改 1 行。

用 AST 读取实际脚本中的 expected 常量，再调用真实 `boot_smoke.Guest.expect` 检查两个预置串：只有回显、回显加输出。七处旧版两个都接受；新版仅接受后者。这个验证只针对输出判定器，没有启动 guest。

行结束依据：Dash console 输入处理显式写 `\n`，debug console 与 UART 路径原样输出 bytes；同仓 Dash B2 也按 `alpha\nbeta\n` 匹配。此处完整结果行使用 LF，与实际输出路径一致。

### T-UL-04：pipe atomic fixture 仍按旧 ABI 拒绝非零截止时间

`tests/fixtures/dash_c1/pipe_atomic.c` 在空 pipe 的 writer 上调用 `sys_pipe_wait(writer, 512, 1)`，仍断言返回 -2。当前第三参是绝对 monotonic deadline：内核 `tasks.cpp` 的 `sys_pipe_wait` 先判断 ready，有至少 512 bytes 可写便返回 0，再在不 ready 时检查 deadline。同目录 `pipe_probe.c` 已按这个行为更新，因此旧 atomic fixture 会提前失败在 `wait-minimum-validation`。

只将这一处期望值从 -2 改成 0。验证命令 `cc -std=gnu11 -fsyntax-only tests/fixtures/dash_c1/pipe_atomic.c` 通过；另核对 `docs/contracts/ssg_p4a_subscriber.md` 已登记绝对截止时间。**此项是旧测试契约修正，未运行 guest，未声称内核行为有 bug。**

### T-UL-05：device ABI runner 从未关闭 Guest

`tests/device_abi_guest.py` 的 `finally` 原来只写报告和 serial，没有调用 `guest.close()`。无论通过还是测试异常，都留下 QEMU 子进程和它打开的临时磁盘。按其他 runner 的现有清理方式，在 `finally` 开头增加一行 `guest.close()`，随后仍保存报告和 serial。验证为实际控制流审阅和 Python `compile` 语法检查；**未启动 guest，也没有额外构造重型生命周期 mock**。

### T-UL-06：三处 ISO 文件检查只匹配输入里的名字

`tests/iso_boot_smoke.py` 与 `iso_file_kernel_smoke.py` 将 `type hello` 后找到 `hello` 当成 file-service 通过。真实 bootstrap 在 `file_ui.cpp::init` 创建的是 `hello.elf`；`execution::resolve` 按原命令名查询而不追加后缀，因此正常的 `xsh: hello: not found` 也满足旧断言。两脚本分别改 2 行：发送 `type hello.elf`，期待真正的 `hello.elf -> /hello.elf` 解析结果。

`tests/iso_bundle_install.py` 的 `stat /usr/bin/dash` 也只等 `dash`，输入回显就满足。按实际 `ui::stat` 输出，改一行等待 `/usr/bin/dash size=`。

三处用实际 AST 常量和 `Guest.expect` 验证：旧版接受包含 not found / stat error 的失败输出，新版拒绝失败输出，接受真实解析结果或 stat size 输出。与 T-UL-03 合计 **10 个标记位置**：基线接受 10/10 假输出，修后拒绝 10/10 假输出并接受 10/10 正确输出。没有运行 ISO 客体。

## 已修正的参考模型

### M01：IPC caller-first 排队路径丢失调用方 badge

`tests/ipc_v1_reference_model.py` 的 receive-first 路径用调用方 capability badge，caller-first 则把接收方 capability badge 传给 `_deliver`。实际模型调用 `create(10) → delegate(...20, rights.call, 0xabc) → submit_call → begin_receive` 得到 0，期望为 2748（0xabc）。旧测试只覆盖 receive-first 的 badge。

修正为在 `call_record` 保存调用方 badge，排队 delivery 使用该字段，合计 3 行模型改动；在原 unittest 加 6 行 caller-first 用例。新用例在旧模型失败 `0 != 2748`，修后 `python3 tests/ipc_v1_reference_model.py` 的 19 项全部通过。**这是宿主参考模型的缺陷与修复，未修改内核、SDK 或 IPC feature bits，不据此声称真实内核 IPC 已验证。**

## 必须保留的测试覆盖边界

- `tests/audio_client_host_test.cpp` 的 `service_rejects` 明确复制了服务请求校验，测试本身调用真实 SDK，但“service_accepts_all=1”证明的是这个宿主模型与请求的一致性；不能单凭它声称真实 audio_service 已接受全部请求。`audio_service_reply_test.cpp` 另有真实服务 handler 测试。本轮按根代理指令只记录边界，不重构既有测试。
- CPython 各阶段、文件 POSIX、shell launch、编译器集成等脚本需要对应 SDK/解释器/包缓存和真实 guest。阅读完整、宿主语法通过或其他宿主测试通过均不等价于这些 guest 门禁通过。
- CPython `syntax_error.py`、C/C++ `syntax_error`、`link_error`、`header_error` 等是预期负例，不能在全仓编译检查中误判为产品源码缺陷。

## 审阅进度

本组独立补读 271 个文件，清单无重复、全部路径存在。运行时和构建阶段清单 `userland_audit_files.txt` 已整理为 104 个纯路径，包含 92 个用户态文件与 12 个脚本；这两份清单保持分开，便于根代理去重统计。额外 35 个委派项由 UI 组独立记录，不冒充本组全文阅读。

本组补审改动涉及 13 个原测试文件，新增 1 个 Python 测试文件。修复按 6 个测试流程/判定问题与 1 个参考模型问题分类；T-UL-03、T-UL-06 内的多个受影响位置不重复计成产品缺陷。本阶段永久新增 unittest 为 binutils 3 项、IPC 1 项，共 4 项；执行的 IPC 全套 19 项包含原有 18 项。第一阶段用户态组的 85 case 另见 `userland_audit_report.md`，不与这批重复相加制造一个“全部新测试”数字。

## 可重复验证命令

从仓库根执行：

```sh
python3 tests/binutils_stress_exit_test.py
python3 tests/ipc_v1_reference_model.py
cc -std=gnu11 -fsyntax-only tests/fixtures/dash_c1/pipe_atomic.c

python3 - <<'PY'
from pathlib import Path
paths = [
    'binutils_stress.py', 'dash_preinstall_smoke.py', 'utf8_dash_smoke.py',
    'device_abi_guest.py', 'ipc_v1_reference_model.py', 'shell_launch_sl3_make.py',
    'iso_boot_smoke.py', 'iso_capacity_smoke.py', 'iso_dash_install.py',
    'iso_file_kernel_smoke.py', 'iso_bundle_install.py', 'iso_bundle_reboot.py',
    'binutils_stress_exit_test.py',
]
for name in paths:
    path = Path('tests') / name
    compile(path.read_text(), str(path), 'exec')
print('PASS 13 Python source syntax checks')
PY
```

已观察结果分别为 unittest 3/3、19/19 通过，C 语法检查成功，Python 13 文件语法检查成功。相关已跟踪改动 `git diff --check` 通过。没有运行这些 runner 的 guest、跨编译 SDK 或实际硬件测试。

以下是输出判定器的可重复边界检查；只有进程退出边界使用最小对象，期望值从实际源码 AST 提取，匹配逻辑调用真实 `Guest.expect`，未复制测试的业务判定实现。

```sh
python3 - <<'PY'
import ast
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
sys.path.insert(0, 'tests')
from boot_smoke import Guest
cases = [
    ('dash_preinstall_smoke.py', b'PREINSTALLED_DASH', b'\nPREINSTALLED_DASH\n', b'echo PREINSTALLED_DASH\n$ ', b'echo PREINSTALLED_DASH\nPREINSTALLED_DASH\n$ '),
    ('utf8_dash_smoke.py', '你好'.encode(), '\n你好\n'.encode(), 'echo 你好\n$ '.encode(), 'echo 你好\n你好\n$ '.encode()),
    ('iso_capacity_smoke.py', b'ISO_CAPACITY_OK', b'\nISO_CAPACITY_OK\n', b'echo ISO_CAPACITY_OK\n$ ', b'echo ISO_CAPACITY_OK\nISO_CAPACITY_OK\n$ '),
    ('iso_dash_install.py', b'A3DASH', b'\nA3DASH\n', b'echo A3DASH\n$ ', b'echo A3DASH\nA3DASH\n$ '),
    ('iso_bundle_install.py', b'BUNDLEDASH', b'\nBUNDLEDASH\n', b'echo BUNDLEDASH\n$ ', b'echo BUNDLEDASH\nBUNDLEDASH\n$ '),
    ('iso_bundle_reboot.py', b'FIRSTBOOT', b'\nFIRSTBOOT\n', b'echo FIRSTBOOT\n$ ', b'echo FIRSTBOOT\nFIRSTBOOT\n$ '),
    ('iso_bundle_reboot.py', b'SECONDBOOT', b'\nSECONDBOOT\n', b'echo SECONDBOOT\n$ ', b'echo SECONDBOOT\nSECONDBOOT\n$ '),
    ('iso_boot_smoke.py', b'hello', b'hello.elf -> /hello.elf', b'type hello.elf\nxsh: hello.elf: not found\nxsh> ', b'type hello.elf\nhello.elf -> /hello.elf\nxsh> '),
    ('iso_file_kernel_smoke.py', b'hello', b'hello.elf -> /hello.elf', b'type hello.elf\nxsh: hello.elf: not found\nxsh> ', b'type hello.elf\nhello.elf -> /hello.elf\nxsh> '),
    ('iso_bundle_install.py', b'dash', b'/usr/bin/dash size=', b'stat /usr/bin/dash\n[files] stat error=-1\nxsh> ', b'stat /usr/bin/dash\n/usr/bin/dash size=4096 version=1\nxsh> '),
]
def expected(source, value):
    nodes = [n.value for n in ast.walk(ast.parse(source))
             if isinstance(n, ast.Constant) and n.value == value]
    assert len(nodes) == 1, (value, len(nodes))
    return nodes[0]
def accepts(marker, output):
    guest = Guest.__new__(Guest)
    guest.name = 'output_boundary'
    guest.output = bytearray(output)
    guest.process = SimpleNamespace(poll=lambda: 0, returncode=0)
    try:
        guest.expect(marker)
        return True
    except AssertionError:
        return False
for name, old, new, failure, success in cases:
    path = 'tests/' + name
    baseline = subprocess.check_output(
        ['git', 'show', 'a676e21292fc322de0814aaaeee80819e41371ba:' + path], text=True)
    revised = Path(path).read_text()
    assert accepts(expected(baseline, old), failure), name
    assert not accepts(expected(revised, new), failure), name
    assert accepts(expected(revised, new), success), name
print('PASS 10 markers: old false output accepted; new false output rejected; new correct output accepted')
PY
```
