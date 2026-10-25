# 0030：CPython PY0a/PY0b

2026-10-25。用户要求接手意外暂停的 CPython 移植。上一轮已冻结 3.14.9 源码并在
`src/ports/cpython/` 下建立配置、补丁和 `scripts/build_cpython.py`，但 11 个
cache fingerprint 都停在 `compile_probe_failed`，最后失败点是
`Modules/posixmodule.c` 的 `lstat`。本轮在 0030 已登记的移植范围内继续，占用
`src/ports/cpython/`、`scripts/build_cpython.py`、`tests/cpython_py0b_smoke.py`、
本记录、`docs/state.md` 和 CPython 相关说明；没有修改 libc、内核、loader、
dash/sbase、发布镜像或日常盘，也没有并发运行共享 `make build`。

## 结果

PY0a 和 PY0b 均已通过：

- 构建 fingerprint `ad85d8438b4101d66483`，冻结 SDK build
  `2c3876e640840ff5`（`build/releases/0.0.1-1024/sdk`）。
- `target_build/python.exe`：ELF64 x86-64，静态，未 strip
  `bc7aeca3521306a842e58b034671b06d896c79118f0c5c4766949fab4f42cf82`，
  42794920 字节；strip 后 `71839cb770549e47d709d4cd2de3bf3668ba29569a35a30933523cc641fed1c5`，
  7928480 字节。
- 客体报告 `build/cpython_py0b_report.json`，7/7 检查通过：`-c` 算术、脚本文件、
  Unicode、未捕获异常退出 1、GC、同目录 import、重复启动。运行镜像
  `build/xos.img`，build `498ad82e530fbf23`，SHA256
  `66a9885922414fe400ca1d7f1e68716638b6a931d46e0ce5c504b0f5c960ae4d`。
- 安装到客体的标准库子集 558 个文件（排除 `test/`、`idlelib/`、`tkinter/`、
  `turtledemo/`、`ensurepip/`、`lib2to3/`），解释器位于 `/usr/bin/python3`，
  标准库位于 `/usr/lib/python3.14/`。

## 修掉的真实缺口

以下是本轮从链接/启动失败中定位并写入 `patches/0002_xos_module_scope.patch`
或 `config/xos_config.site` 的内容：

1. **lstat**：`DirEntry_fetch_stat` 在 XOS 上直接调用不存在的 `lstat`。XOS 无符号
   链接，改为 `stat`。
2. **tz 变量**：newlib 只声明 `_timezone`/`_daylight`/`_tzname`，CPython 用 POSIX
   名字。XOS 分支改用 newlib 名字；没有 zoneinfo，值保持 UTC/无 DST。
3. **clock()/times()**：newlib 的 `clock()` 经 `_times_r` 调用公共 `times()`，SDK
   没有该符号。`xos_time.cpp` 提供 `times()`，转调 `_times()` 的 ENOSYS，因此
   `time.process_time()` 运行时报错而不是返回假 CPU 时间。`HAVE_TIMES` 显式关闭，
   避免 `sysconf(_SC_CLK_TCK)` 启动失败。
4. **ticks_per_second**：`posix` 模块初始化无条件读取该值。XOS 分支直接使用
   `CLOCKS_PER_SEC`，与 newlib `clock()` 一致。
5. **resource/模块范围**：SDK 的 `sys/resource.h` 只有 `getrusage`，没有 rlimit。
   XOS 在 configure 中把 `resource`、`select`、`_posixsubprocess`、PTY、dbm、
   curses、tkinter 等无底座模块标为 n/a；静态构建是唯一可选类型。
6. **链接顺序**：模块归档（libmpdec/HACL*/expat）排在 `LIBS` 之后，`libc.a`/
   `libgcc.a` 无法回扫。所有链接规则统一包一层 `--start-group/--end-group`。
7. **缺失 libc 符号**：chroot/link/symlink/fchdir/fsync/fdatasync/setgroups/fork/
   sched.h 在交叉 configure 中是假阳性（只编译不链接）。已在 config.site 显式
   置 no，并由 0002 去掉 `pause()`、`lstat` 的引用。
8. **哈希种子**：XOS 尚无熵服务。bootstrap profile 在未显式设置 `PYTHONHASHSEED`
   时使用固定种子 0，并在文档标明这不是安全随机。
9. **time.sleep()**：没有阻塞定时器，`xos_cpython_sleep_ns()` 自旋等待 PIT tick；
   延时真实存在但占用 CPU。
10. **`-c` 需要 linecache**：CPython 3.14 会把交互/`-c` 源码注册到 `linecache`，
    最小标准库必须带 `linecache.py`。
11. **栈**：`-O0` 构建在 import 阶段溢出 128 KiB 用户栈；改用 `-O2` 后通过。

## 实际命令

```sh
SDK=build/releases/0.0.1-1024/sdk
/usr/bin/python3 scripts/build_cpython.py \
  --archive .cache/xos_seed/cpython/sources/Python-3.14.9.tar.xz \
  --sdk "$SDK" \
  --build-python .cache/xos_seed/cpython/host_build/python.exe \
  --compile-probe
/usr/bin/python3 tests/cpython_py0b_smoke.py
```

宿主工具：GCC/G++ 16.2.0、Binutils 2.47.20260726、QEMU 11.1.2、宿主 Python
3.12。configure 行与完整参数保存在各 fingerprint 的 `py0a_report.json`。
`make` 摘要：114 个模块，71 个静态内建、0 个共享、25 个 n/a、9 个禁用、
9 个缺失、0 个导入失败。

## 未完成与限制

- 固定哈希种子、自旋 sleep、无墙钟（`gettimeofday` 仍 ENOSYS）、无 CPU 时间、
  无 fork/exec/select/动态加载/线程。上述能力不由本组伪造。
- 传统 REPL、`input()`、Ctrl-D、Escape 取消和持久化 JSON 尚未验证（PY2）。
- 脚本的 argv/cwd/env、同目录 import 的路径规则和标准库闭包清单尚未冻结（PY1）。
- 全量标准库未安装；`lib-dynload` 不存在，启动会打印
  `Could not find platform dependent libraries <exec_prefix>`，当前无害。
- 未重跑旧压力、未改共享发布镜像；E08/dash 证据不受本轮影响。

## 下一步

1. PY1：脚本 argv/cwd/env、工作盘目录/文件 API、同目录 import 与标准库闭包清单，
   并把安装布局做成可复现的 stage/manifest。
2. PY2：`PYTHON_BASIC_REPL`、`input()` 的空闲/EOF/退格、JSON 存档、sync 后重启。
3. 熵与时间：在公共层提供真实熵/墙钟后再关闭固定种子和自旋 sleep；安全随机
   单独 gate，不以开发 profile 冒充。
4. E13-T 的 T2 冻结后接 T3-PY 真实 pthread；本组未提前伪 pthread。
