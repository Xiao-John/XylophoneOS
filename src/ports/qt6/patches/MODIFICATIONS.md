# Qt6 补丁修改标注（MODIFICATIONS.md）

## 用途与口径

本文件按 GPLv3 §5(b) / LGPLv3 §2 的修改通知要求，对 `src/ports/qt6/patches/` 下
**全部 10 个补丁**逐个标注修改情况，用于分发时的修改通知义务。

数据口径（全部实测，未查到的字段写 NOT_RUN，未做任何推测性补全）：

- **触及的上游文件**：取各补丁正文的 `---` / `+++` 行实测提取。
- **增删行数**：统计补丁正文中以 `+` / `-` 开头的行，剔除 `---` / `+++` 文件头行；
  空增行/空删行计入。
- **补丁头日期与作者**：10 个补丁文件均**无补丁头**（无 `From` / `Date` / `Author` /
  `Subject` 行，文件以 diff 正文直接开始），故该字段一律 **NOT_RUN**。
- **引入分支/时间/作者**：`git log -- <patch>` 实测（只读查询）。
- **显著修改判定**（本文件内部事实口径，非法律结论）：
  - **显著**：删除或改写上游既有代码行，或改变 XOS 上的可观察行为、构建产物组成。
  - **轻微**：仅新增条件分支 / 宏定义 / 头文件包含，不改动其他平台的既有代码路径。
- 全部 10 个补丁内 **0 处**自带修改标注行（grep `+.*SPDX|+.*Copyright|+.*Date:` 命中
  均为 0），即补丁 hunk 内尚无"改动 + 日期"的显著标注；本文件即为该通知的集中标注。

---

## 逐补丁标注

### 1. `0001-xos-platform-detection.patch`

- **触及的上游文件**（`---`/`+++` 实测，1 个）：`src/corelib/global/qsystemdetection.h`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在 Qt 平台检测宏链中新增分支——检测到 `__XOS__`
  时定义 `Q_OS_XOS`，使后续所有 `Q_OS_XOS` 条件编译可以生效。
- **增删行数**：+2 / -0（该文件 +2 / -0）
- **是否显著修改**：轻微。依据：仅新增一个 `#elif` 分支与一条 `#define`，未删除或
  改写任何既有平台（Linux/FreeBSD 等）的检测逻辑，其他平台行为不变。
- **引入**：分支 `main`（经 PR #8 合入）；当前检出分支 `codex/d7_license_release_prep`
  亦包含该提交。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 2. `0002-xos-event-dispatcher-selection.patch`

- **触及的上游文件**（实测，7 个）：
  `src/corelib/configure.cmake`、`src/corelib/CMakeLists.txt`、
  `src/corelib/thread/qthread_unix.cpp`、`src/corelib/kernel/qcoreapplication.cpp`、
  `src/corelib/kernel/qcore_unix.cpp`、`src/corelib/thread/qmutex_p.h`、
  `src/corelib/thread/qmutex.cpp`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：为 XOS 选择自定义事件分发器并接通配套改动：
  - `configure.cmake`：`CMAKE_SYSTEM_NAME STREQUAL "XOS"` 时豁免
    "Qt requires poll()/ppoll()/poll_ts()/select()" 的 ERROR 检查。
  - `CMakeLists.txt`：XOS 下改用 `kernel/qeventdispatcher_xos.cpp`、
    `global/qxos_unsupported.cpp`、`io/qstorageinfo_stub.cpp`，并把
    `qeventdispatcher_unix.cpp`、`qmutex_unix.cpp`、`qstorageinfo_unix.cpp`
    排除出 XOS 构建。
  - `qthread_unix.cpp`：XOS 创建 `QEventDispatcherXos`；XOS 不包含
    `qeventdispatcher_unix_p.h`；线程收尾在 XOS 上不用 `pthread_cleanup_push/pop`
    而直接调用 `finish()`；`QThread::setTerminationEnabled` 在 XOS 上仅告警
    "thread cancellation is unsupported on XOS"。
  - `qcoreapplication.cpp`：XOS 不包含 unix dispatcher 头，跳过 setuid
    (`geteuid()!=getuid()`) 的 `qFatal` 检查。
  - `qcore_unix.cpp`：XOS 下 `qt_ignore_sigpipe()` 作空实现（注释：XOS 管道报
    EPIPE、不产生 POSIX SIGPIPE），并跳过 `ppoll/pollts` 相关段。
  - `qmutex_p.h` / `qmutex.cpp`：XOS 用 `pthread_mutex_t`/`pthread_cond_t` 计数
    互斥实现替代 `sem_t`，`qmutex.cpp` 在 XOS 下 `#include "qmutex_xos.cpp"`。
  - 说明：补丁引用但不含于补丁内的 `qeventdispatcher_xos.cpp`、
    `qeventdispatcher_xos_p.h`、`qmutex_xos.cpp`、`qxos_unsupported.cpp`
    由 `src/ports/qt6/prepare_source.py` 从 `src/ports/qt6/runtime/` 复制进源码树
    （该脚本第 58–61 行）；`io/qstorageinfo_stub.cpp` 的来源 **NOT_RUN**
    （本仓端口脚本内未检索到该文件的生成/复制来源）。
- **增删行数**：+48 / -11。分文件：
  `configure.cmake` +1/-1；`CMakeLists.txt` +15/-3；`qthread_unix.cpp` +17/-4；
  `qcoreapplication.cpp` +2/-2；`qcore_unix.cpp` +5/-1；`qmutex_p.h` +6/-0；
  `qmutex.cpp` +2/-0。
- **是否显著修改**：显著。依据：改写线程收尾与线程取消语义（删除/条件化
  `pthread_cleanup_push`/`pop`、`setTerminationEnabled` 退化为告警）、改变互斥量
  实现选择、跳过 SIGPIPE 与 setuid 安全检查、并改变 Core 目标的源文件组成；
  这些均为对上游既有代码路径的删除或改写，且改变 XOS 上的可观察行为。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 3. `0003-xos-system-info.patch`

- **触及的上游文件**（实测，1 个）：`src/corelib/global/qsysinfo.cpp`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：为 XOS 提供 QSysInfo 各 API 的返回值——
  避免包含 `sys/utsname.h`；`currentCpuArchitecture()` 在 XOS 走
  `buildCpuArchitecture()`；`kernelType()` 返回 `"xos"`；`kernelVersion()` 返回
  空（注释：no kernel version API）；`prettyProductName()` 返回 `"XylophoneOS"`；
  `machineHostName()` 返回空（注释：no hostname service）。
- **增删行数**：+16 / -4（该文件 +16 / -4）
- **是否显著修改**：显著。依据：`kernelType`、`kernelVersion`、
  `prettyProductName`、`machineHostName`、`currentCpuArchitecture` 五个公开 API
  在 XOS 上的可观察返回值被改写（既有 `#if`/`#elif` 行被替换以插入 XOS 分支）。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 4. `0004-xos-environment.patch`

- **触及的上游文件**（实测，1 个）：`src/corelib/global/qtenvironmentvariables.cpp`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在 `qputenv` 与 `qunsetenv` 的条件表达式中
  追加 `|| defined(Q_OS_XOS)`，使 XOS 走 POSIX.1-2001 的 `setenv`/`unsetenv` 实现。
- **增删行数**：+2 / -2（该文件 +2 / -2）
- **是否显著修改**：轻微。依据：仅扩展两处条件编译表达式，不删除既有逻辑；
  其他平台分支不变，XOS 上只是启用与 POSIX 相同的既有实现。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 5. `0005-xos-no-mmap.patch`

- **触及的上游文件**（实测，3 个）：`src/corelib/io/qresource.cpp`、
  `src/corelib/io/qfsfileengine_unix.cpp`、`src/corelib/kernel/qtranslator.cpp`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在 XOS 上禁用 mmap 路径——
  - `qresource.cpp`：XOS 不定义 `QT_USE_MMAP`、不包含 `sys/mman.h`；
    `mapUncompressed_sys()` 直接 `return false`，`unmapUncompressed_sys()` 仅
    `Q_ASSERT(!mustUnmap)`，页边界辅助函数 `mappingBoundaries` 在 XOS 下不编译。
  - `qfsfileengine_unix.cpp`：XOS 不包含 `sys/mman.h`；`map()` 返回 `nullptr`
    并置 `QFile::UnspecifiedError`/`ENOTSUP`；`unmap()` 在 XOS 下为空操作。
  - `qtranslator.cpp`：XOS 不定义 `QT_USE_MMAP`（翻译文件不走内存映射）。
- **增删行数**：+22 / -3。分文件：`qresource.cpp` +11/-1；
  `qfsfileengine_unix.cpp` +10/-1；`qtranslator.cpp` +1/-1。
- **是否显著修改**：显著。依据：删除/条件化 `sys/mman.h` 包含与 mmap 使用点，
  `QFile::map` 在 XOS 上从"内存映射成功"改为"返回错误"，可观察行为改变。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 6. `0006-xos-sha3-endian.patch`

- **触及的上游文件**（实测，1 个）：`src/3rdparty/sha3/brg_endian.h`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在字节序探测的头文件选择链中新增
  `__XOS__` 分支，`#include <machine/endian.h>` 以获取字节序宏。
- **增删行数**：+2 / -0（该文件 +2 / -0）
- **是否显著修改**：轻微。依据：仅新增一个 `#elif` 分支与一条 `#include`，
  不改动其他平台（Sun/FreeBSD/Apple 等）的既有分支。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 7. `0007-xos-filesystem.patch`

- **触及的上游文件**（实测，2 个）：`src/corelib/io/qfilesystemengine_unix.cpp`、
  `src/corelib/io/qstandardpaths_unix.cpp`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在 XOS 上禁用尚无对应原语的文件系统能力——
  - `qfilesystemengine_unix.cpp`：`canonicalName()` 在 XOS 置 `errno=ENOTSUP`
    并返回空项；`renameFile()` 在 XOS 返回 `false`（注释：no proven atomic
    rename-no-replace primitive）；`moveFileToTrash()` 在 XOS 走桩实现
    （与 bootstrapped/Android/VXWORKS 同一分支）。
  - `qstandardpaths_unix.cpp`：`checkXdgRuntimeDir()` 在 XOS 恒 `false`
    （注释：no per-user ownership or permission model）；`RuntimeLocation`
    在 XOS 返回空。
- **增删行数**：+22 / -1。分文件：`qfilesystemengine_unix.cpp` +13/-1；
  `qstandardpaths_unix.cpp` +9/-0。
- **是否显著修改**：显著。依据：`canonicalName`、`renameFile`、
  `writableLocation(RuntimeLocation)` 等既有函数的返回值/行为在 XOS 上被改写
  为禁用或空结果，且原实现被 `#else` 包裹绕过。
- **引入**：分支 `main`（经 PR #8 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `7a7481f210bcab83b0efda46878d6aa7e9fe7f20`，
  2026-10-28 14:11:19 +0800，Perry \<www080327@qq.com\>，
  "E15/G01/G03: run QtCore 6.8.3 in XOS (#8)"。

### 8. `0008-xos-gui-platform.patch`

- **触及的上游文件**（实测，3 个）：`src/3rdparty/freetype/CMakeLists.txt`、
  `src/gui/CMakeLists.txt`、`src/3rdparty/harfbuzz-ng/CMakeLists.txt`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：按 XOS 裁剪 QtGui 与捆绑第三方库的构建组成——
  - `freetype/CMakeLists.txt`：XOS 使用 `src/base/ftsystem.c`（原 WIN32 分支），
    不再编译 `builds/unix/ftsystem.c`（unix 版需 mmap）。
  - `gui/CMakeLists.txt`：6 处 `qt_internal_extend_target(Gui …)` 条件加
    `AND NOT CMAKE_SYSTEM_NAME STREQUAL "XOS"`，排除 unix 字体数据库头、
    `qunixnativeinterface.cpp`、`qgenericunixeventdispatcher.cpp`/
    `qunixeventdispatcher.cpp`、`qgenericunixservices.cpp`、`qtx11extras.cpp`、
    `qgenericunixthemes.cpp`。
  - `harfbuzz-ng/CMakeLists.txt`：新增 XOS 条件目标段，加入
    `src/graph/gsubgpos-context.cc`（注释：XOS static symbol closure，
    subset/repacker 需要这些上游定义）。
- **增删行数**：+14 / -8。分文件：`freetype/CMakeLists.txt` +2/-2；
  `gui/CMakeLists.txt` +6/-6；`harfbuzz-ng/CMakeLists.txt` +6/-0。
- **是否显著修改**：显著。依据：改写多个 `qt_internal_extend_target` 的条件并
  新增源文件条目，直接改变 XOS 构建产物的成员组成（哪些上游源文件被编译）；
  既有条件行被替换。
- **引入**：分支 `main`（经 PR #9 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `be1e9c1a37f217463b110fe3607ca06fb6ee5a44`，
  2026-10-28 15:40:26 +0800，Perry \<www080327@qq.com\>
  （co-authored-by: Xiao-John \<75989255+Xiao-John@users.noreply.github.com\>），
  "E16/G04: run QtGui 6.8.3 with static XOS raster QPA (#9)"。

### 9. `0009-xos-freetype-no-mmap.patch`

- **触及的上游文件**（实测，1 个）：`src/3rdparty/freetype/builds/unix/ftsystem.c`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：删除 FreeType unix 系统层的 mmap 支持——
  移除 `sys/mman.h` 包含、`MUNMAP_*` 宏、`munmap` 声明与
  `ft_close_stream_by_munmap()` 函数；文件打开处删除 `mmap(...)` 调用与
  `stream->close = ft_close_stream_by_munmap` 赋值，改为 `if ( 1 )` 恒走
  顺序读取回退路径。
- **增删行数**：+1 / -57（该文件 +1 / -57）
- **是否显著修改**：显著。依据：大量删除上游既有代码（-57 行，含整个
  `ft_close_stream_by_munmap` 函数），并以 `if (1)` 改写原 mmap 成败分支，
  上游文件内容被实质性删改。
- **引入**：分支 `main`（经 PR #52 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `8ec04891f18d2c7bfa8629f25e2d1fd39233712f`，
  2026-10-31 21:12:09 +0800，Xiao-John \<75989255+Xiao-John@users.noreply.github.com\>，
  "tech debt C6: guest re-qualification of the B1 rename (4 suites PASSED) + target-Qt build fixes (#52)"。

### 10. `0010-xos-host-arm64-acle.patch`

- **触及的上游文件**（实测，1 个）：`src/corelib/thread/qyieldcpu.h`
- **补丁头日期与作者**：NOT_RUN（无补丁头）
- **修改目的**（读补丁内容归纳）：在 host 为 arm64/aarch64 且编译器提供
  `<arm_acle.h>` 时包含该头（注释：Apple clang>=21 declares `__yield` only via
  the ACLE header），使 `qYieldCpu()` 的实现能拿到 `__yield` 声明。
- **增删行数**：+4 / -0（该文件 +4 / -0）
- **是否显著修改**：轻微。依据：仅新增一个条件 `#include` 块，不删除或改写
  既有代码；影响限于 host arm64 构建的头文件可见性。
- **引入**：分支 `main`（经 PR #52 合入）；当前分支 `codex/d7_license_release_prep`
  亦包含。提交 `8ec04891f18d2c7bfa8629f25e2d1fd39233712f`，
  2026-10-31 21:12:09 +0800，Xiao-John \<75989255+Xiao-John@users.noreply.github.com\>，
  "tech debt C6: guest re-qualification of the B1 rename (4 suites PASSED) + target-Qt build fixes (#52)"。

---

## 汇总表

| 补丁 | 上游文件数 | 增行 | 删行 | 显著性 | 引入提交（短） | 引入日期（+0800） | 引入者 / PR |
|---|---|---|---|---|---|---|---|
| 0001-xos-platform-detection | 1 | +2 | -0 | 轻微 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0002-xos-event-dispatcher-selection | 7 | +48 | -11 | 显著 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0003-xos-system-info | 1 | +16 | -4 | 显著 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0004-xos-environment | 1 | +2 | -2 | 轻微 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0005-xos-no-mmap | 3 | +22 | -3 | 显著 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0006-xos-sha3-endian | 1 | +2 | -0 | 轻微 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0007-xos-filesystem | 2 | +22 | -1 | 显著 | `7a7481f` | 2026-10-28 14:11:19 | Perry / #8 |
| 0008-xos-gui-platform | 3 | +14 | -8 | 显著 | `be1e9c1` | 2026-10-28 15:40:26 | Perry（co: Xiao-John）/ #9 |
| 0009-xos-freetype-no-mmap | 1 | +1 | -57 | 显著 | `8ec0489` | 2026-10-31 21:12:09 | Xiao-John / #52 |
| 0010-xos-host-arm64-acle | 1 | +4 | -0 | 轻微 | `8ec0489` | 2026-10-31 21:12:09 | Xiao-John / #52 |
| **合计** | **21**（唯一上游文件 21，无跨补丁重复） | **+133** | **-86** | 显著 6 / 轻微 4 | — | — | — |

- 补丁数：**10**；触及上游文件条目：21；唯一上游文件：**21**（无文件被多个补丁触及）。
- 引入分支：三个引入提交均为 `origin/main` 的祖先（PR #8 / #9 / #52 合入 main）；
  当前检出分支 `codex/d7_license_release_prep` 亦包含全部三个提交。
- 补丁头日期与作者：**10/10 为 NOT_RUN**（补丁文件无头）。
- 其他 NOT_RUN：`0002` 引用的 `src/corelib/io/qstorageinfo_stub.cpp` 在本仓端口
  脚本内未检索到生成/复制来源，其来源 **NOT_RUN**。

---

## 上游文件清单（唯一 21 个，来自各补丁 `---`/`+++` 实测）

| # | 上游文件 | 触及补丁 |
|---|---|---|
| 1 | `src/3rdparty/freetype/CMakeLists.txt` | 0008 |
| 2 | `src/3rdparty/freetype/builds/unix/ftsystem.c` | 0009 |
| 3 | `src/3rdparty/harfbuzz-ng/CMakeLists.txt` | 0008 |
| 4 | `src/3rdparty/sha3/brg_endian.h` | 0006 |
| 5 | `src/corelib/CMakeLists.txt` | 0002 |
| 6 | `src/corelib/configure.cmake` | 0002 |
| 7 | `src/corelib/global/qsysinfo.cpp` | 0003 |
| 8 | `src/corelib/global/qsystemdetection.h` | 0001 |
| 9 | `src/corelib/global/qtenvironmentvariables.cpp` | 0004 |
| 10 | `src/corelib/io/qfilesystemengine_unix.cpp` | 0007 |
| 11 | `src/corelib/io/qfsfileengine_unix.cpp` | 0005 |
| 12 | `src/corelib/io/qresource.cpp` | 0005 |
| 13 | `src/corelib/io/qstandardpaths_unix.cpp` | 0007 |
| 14 | `src/corelib/kernel/qcore_unix.cpp` | 0002 |
| 15 | `src/corelib/kernel/qcoreapplication.cpp` | 0002 |
| 16 | `src/corelib/kernel/qtranslator.cpp` | 0005 |
| 17 | `src/corelib/thread/qmutex.cpp` | 0002 |
| 18 | `src/corelib/thread/qmutex_p.h` | 0002 |
| 19 | `src/corelib/thread/qthread_unix.cpp` | 0002 |
| 20 | `src/corelib/thread/qyieldcpu.h` | 0010 |
| 21 | `src/gui/CMakeLists.txt` | 0008 |

---

## 声明

**本标注用于分发时的修改通知；当前不随包分发 Qt 二进制，义务未触发；
本文件不是法律意见。**
