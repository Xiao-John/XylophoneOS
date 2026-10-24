# E08-4/5 GCC Seed 交接页

状态：**C Seed 已构建并安装，客体 gate 未运行**。角色：工具链协作者（secondary prompt）。
本页是唯一共享交接入口；不修改 `build/`、`build/sdk`、内核、用户运行库、共享测试或主状态。

## 输入合同

- 系统/运行时构建：`b1ded17e673ccffc`（E08-2/3 修复版）。
- SDK 快照（主端 2026-10-24 新发）：`.cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`
  （manifest SHA256 `f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74`，
  快照 metadata build_id `10306f6414f8d488`；主端说明系统构建 `9830f208...`）。
  旧 SDK `f1876914...` 只保留为历史预检输入。
- 已修复 binutils Seed：`a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479`
  （不要复用含文件偏移 bug 的 `47ddd307...`）。
- 新 SDK 已用于本页下方 libstdc++/GCC 构建；未修改快照。

## 构建目标（C Seed 先行）

- build：arm64 macOS（`config.guess` 实际值）。
- host / target：`x86_64-unknown-elf` / `x86_64-elf`（与 binutils Seed 一致；
  宿主别名不是 Linux ABI）。
- 先 `--enable-languages=c`、静态、无 bootstrap；C++/libstdc++/异常/RTTI/TLS
  只做 E08-5 准备，不把 C 成功写成 G++ 成功。
- 输出只写 `.cache/xos_seed/gcc/`；计划安装
  `install/usr/bin/x86_64-elf-gcc`、`cc1`、`collect2`、`libgcc` 等，并生成
  manifest 记录 SDK/CRT/libgcc/依赖/补丁/实际命令/许可证。

## host C++ runtime（2026-10-24 新 SDK）

已用 GCC 16.2.0 源码的真实 `libstdc++-v3` 在本机交叉构建、安装到私有前缀：

- prefix：`.cache/xos_seed/gcc/stdcxx/prefix`
- headers：`include/c++/16.2.0`（含 `x86_64-unknown-elf/bits/c++config.h`）
- `libstdc++.a`：199 个真实上游对象，5.3 MiB
- `libsupc++.a`：67 个真实上游对象，317 KiB
- 配置/构建：build=本机 `aarch64-apple-darwin27.0.0`，host=`x86_64-unknown-elf`，
  target=`x86_64-elf`，`--with-newlib --disable-shared --enable-static`、
  `--disable-libstdcxx-pch/time/backtrace/verbose`，使用 XOS SDK 包装器。
- 已知工作项（均记录在私有日志，不伪装成完整 C++）：
  - SDK `dirent` 只有 `DT_UNKNOWN/DIR/REG`，用私有 `xos_dirent_compat.h`
    补齐名称常量；不声称 XOS 有 special files/symlinks。
  - libstdc++ 的 C++23 `std`/`std.compat` modules 与当前交叉编译器不兼容，
    本轮 host 闭包跳过 `libmodulesconvenience`；不是 E08-5 完整交付。
  - libtool 生成的 convenience archives 被 macOS `ar` 写成空归档；已用
    `x86_64-elf-ar` 从真实 `.o` 组装 `libstdc++.a`/`libsupc++.a`。
- host 库编译使用 `-fno-exceptions -fno-rtti`；仅用于 GCC 工具自身，
  不代表 target 用户 C++ 的异常/RTTI 基线。

`scripts/build_gcc.py` 已增加 `--stdcxx-prefix`，包装器使用真实 stdcxx headers
（优先于 SDK headers）和静态库；不再使用私有 allocation/utility 替身。

## 当前工作与证据

- 已建立 `src/ports/gcc/{config,patches,upstream}`、`source_lock.json` 与
  `scripts/build_gcc.py`。
- GCC 16.2.0 源码已验证：107,200,820 字节，
  SHA-256 `e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e`；
  GMP 6.3.0 / MPFR 4.2.2 / MPC 1.3.1 的 SHA512 已验证。
- 已实际通过 Canadian-cross configure：build=`aarch64-apple-darwin27.0.0`，
  host=`x86_64-unknown-elf`，target=`x86_64-pc-elf`；
  `--enable-languages=c --with-newlib --without-isl --disable-bootstrap`
  等，使用 SDK `f1876914...`。日志与工作目录
  `.cache/xos_seed/gcc/build/740c2ea862d1ec0dc027f63e259d4b4e3262d908a8a50b9b13ffd584b361feb3/`。
- `make all-gcc` 首次失败在 `libcody`：GCC 自身 C++ 代码需要 `<memory>`，当前
  target libstdc++ 尚未建立。先按 C-only 目标在私有源码打补丁跳过 libcody/
  c++tools 等 C++ 专用 host libs（`src/ports/gcc/patches/0001_...`），不声称
  C++ 已可用。
- 下一次失败在 `libiberty` 的 `lstat`：父 configure 未读取运行时 cache，
  误判 lstat 可用。现已把 `src/ports/gcc/config/xos_cache_seed.sh` 通过
  `CONFIG_SITE` 注入所有子 configure，并重新构建；该 cache 明确 fork/vfork/
  mmap/lstat/dlopen=no、TLS=none。
- 随后 `libcpp` 需要 `<new>`。为 C-only host 构建加了一个**最小 allocation
  shim**（`src/ports/gcc/include/new`、`cxx_runtime.cpp`），只提供
  `operator new/delete`，明确不是 target libstdc++，也没有异常/RTTI 语义。
- 继续 `make all-gcc` 已越过 configure/GMP/libiberty/libcpp，当前阻塞在
  `gcc/c/c-lang.cc` 的 `<algorithm>`：GCC 本体的 C++ 代码需要 target C++
  headers/runtime，**不是**“C 语言前端就能去掉 C++ 依赖”。C-only 只能减少
  用户 C++ 前端，不能消掉 GCC 自身的 C++ 实现。
- 这是 E08-4 对 E08-5 runtime 的真实前置依赖：至少需要 target libstdc++/
  C++ headers（以及其实际运行库），或主 agent 明确批准的等价 C++ 运行环境。
  本次没有用宿主 Mach-O 库或假头文件绕过。
- C Seed 已在此前完成的私有 work `c3b803762179...` 安装；manifest 已生成。
  完整历史失败日志：`build/e08_gcc_seed_build_failure.log`（旧 SDK；私有 cache
  路径同时保留）。

## 已执行的构建与阻塞

1. GCC 16.2.0 源码/依赖校验通过，configure 通过。
2. C-only 跳过 `libcody`/`c++tools` host libs；GCC 的 libiberty 已编译。
3. libiberty `lstat` 通过 XOS_NO_SYMLINKS→stat 补丁解决；不伪装 symlink。
4. libcpp `<new>` 用私有 `<new>`/`operator new/delete` shim 通过；这只是
   host 构建运行库，不是 target libstdc++。
5. host C++ 闭包：用 GCC 16.2.0 真实 `libstdc++-v3` 构建静态
   `libstdc++.a`/`libsupc++.a` 后，`<algorithm>` 等已通过；C Seed 已完成。
   这仍是 **host** 运行闭包，不是 target E08-5 的完整异常/RTTI 声明。
6. `fixincludes` 需要 alarm/execvp，C-only 已跳过；工具链尚无 Seed。

已生成/验证的补丁（均 `patch -p1 --dry-run` 通过）：

- `0001_c_only_skip_cxx_host_libs.patch`
- `0002_libiberty_xos_lstat_stat.patch`
- `0003_libcpp_xos_no_utility_header.patch`
- `0004_c_only_skip_fixincludes.patch`

失败日志：`build/e08_gcc_seed_build_failure.log`；私有工作目录
`.cache/xos_seed/gcc/build/`。没有 build/ 或共享 SDK 修改。

## 预计阻塞（待实际命令验证）

- GCC 本身用 C++ 编写：需区分 **host 编译器执行所需的 C++ 运行库** 与
  target 用户程序的 libstdc++；后者属于 E08-5，不能混为一谈。
- GMP/MPFR/MPC 需要为 host（x86_64-elf）准备；宿主/GCC 构建工具的分工必须
  按 build/host/target 明确，不能拿 Mach-O 工具替代 Seed。
- GCC driver/collect2/pex 可能要求 fork/exec、临时文件、环境、管道、文件权限
  或 sysroot 路径；当前 runtime 只有有限 posix_spawn/pipe/临时文件，需按实际
  调用失败记录，不写假 stub。
- 当前 SDK 只有 newlib、libgcc（宿主交叉）和有限 POSIX 适配；GCC host
  编译器所需 target C++ runtime/headers 尚未成立。
- cc1/collect2 体积、页/堆峰值、工作盘空间需在真实构建后测量；不能用小型
  binutils 的 512 MiB 结果直接外推。

## C Seed 交付（2026-10-24）

- 构建 work：`.cache/xos_seed/gcc/build/c3b803762179aaf5929a6785295b852b014a4e54f0d0f091e1cc04262e8268bf`
- manifest：同目录 `manifest.json`，稳定副本 `src/ports/gcc/seed_manifest.json`（SHA256
  `6c4bbcc5b2753a85e26e5b3ace6cb9ddec93f267021a4bd9c24334a9fc509ff7`），
  schema 2；`install_files` 164 项，每项 `path`/`guest_path`/`sha256`；
  `sysroot_manifest.files` 8 项；`tools` 含 `guest_path`。
- 安装根：同目录 `install/`；guest 路径：
  - `/usr/bin/x86_64-elf-gcc`（3.6 MiB，SHA256
    `4cbf4926f97f22138e7b8c7454f88ad70bdec9d9ed323bc88e4b22733b809ff1`）
  - `/usr/bin/x86_64-elf-cpp`
  - `/usr/libexec/gcc/x86_64-elf/16.2.0/cc1`（45 MiB，SHA256
    `f8aba230636acc6c742d11f617a770d3f294b0596c42617341fe05c40829ba38`）
  - `/usr/libexec/gcc/x86_64-elf/16.2.0/collect2`（2.6 MiB，SHA256
    `920146cc3ced3731327dbab4ce530cd7111f80203e842ef04cabcc2b32dc0326`）
  - `/usr/lib/gcc/x86_64-elf/16.2.0/libgcc.a`（目标 libgcc，1.7 MiB，SHA256
    `1d1755feabef4fbe34527df8f94f44e67f3fc2ce3b1d58dbf824ec858c994dfa`）
    及 `crtbegin.o`/`crtend.o`
- 静态检查：`gcc`/`cc1`/`collect2` 均 ELF64 x86-64 `EXEC`，无 dynamic section。
- 未执行：XOS 客体上的编译/运行；**E08-4 gate 仍 not_run**。
- 已知裁剪/API：
  - `-truncate` 在 XOS 无 `truncate(2)`，驱动显式报不支持，不写成功 stub。
  - SARIF socket sink 用 `XOS_NO_UNIX_SOCKETS` 关闭；文件/文本诊断保留。
  - `gcov`/`gcov-dump`/`gcov-tool` 与 `fixincludes` 不在 C 编译关键路径，
    已显式裁剪；`libdecnumber` 保留并生成 `gstdint.h`。
  - host stdcxx 使用 `-fno-exceptions -fno-rtti`；target E08-5 异常/RTTI/TLS
    尚未完成，不能把 host 库当 target 标准库。

构建命令（私有 cache）：

```sh
python3 scripts/build_gcc.py \
  --sdk .cache/xos_seed/sdk_snapshots/f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74 \
  --expected-sdk-manifest-sha256 f5c74adecb9515878fdbce14a56062cb0567772ae183edecf2a455d15a1f9f74 \
  --stdcxx-prefix .cache/xos_seed/gcc/stdcxx/prefix --jobs 1
```

C Seed 的 host stdcxx 由同源 `libstdc++-v3` 构建；命令/裁剪记录见上节，
`libstdc++.a` SHA256 `f083d386...`，`libsupc++.a` SHA256 `174948f1...`。

## 压力测试设计

E08 最终阶段已压缩为 **E08-post5**：
[reports/e08_post5_plan.md](e08_post5_plan.md)。P0 功能/可用性（C、C++、
工作流、重启）必须全过；P1 健壮性只做 10 轮、规模、2 路并发和有限故障，
不作为放行门槛。旧详细场景 [e08_gcc_stress_plan.md](e08_gcc_stress_plan.md)
仅作参考。测试代码与 build/ 仍归主端。

## 对主 agent 的请求

1. 新 SDK `f5c74ade...` 已接收并在私有 cache 使用；如后续出现 SDK 缺失 API，
   会给出第一处完整诊断、调用点和最小复现，不写假 stub。
2. 确认 `exec-driver`/posix_spawn/pipe/临时文件的实际权限和 ABI；GCC 构建只会
   按真实调用点使用。
3. C Seed 产出后指派隔离窗口做客体 C gate；本协作者不跑 QEMU。
4. 许可证：GCC、GMP、MPFR、MPC、newlib 及运行库例外的实际材料/哈希由本页
   收集后交主 agent 集成，不在本轮宣称完成法律审查。

## 下一步

1. 主 agent 将 manifest 的 `/usr` 安装清单装入临时盘，配 `as`/`ld`/`ar`
   Seed 与 SDK，在隔离窗口运行 C Seed 客体 gate；本协作者不跑 QEMU。
2. gate 若缺 `truncate`/socket/`fixincludes` 之外的真实 API，按调用点补新 SDK；
   本页先记录，不写假 stub。
3. target libstdc++/异常/RTTI/TLS 的 E08-5 正式 gate 仍在 E08-4 通过后。

## 主端0020接收验收补记

原始交付历史保留。主端已修复实际客体暴露的lrealpath、O_NOCTTY、as安装与
会话打开容量问题，独立派生Seed open_capacity_fix/，SDK v4为1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490。
最终82ffcecab8ccbcce下C功能gate通过4组/15命令；collect2未重链接且未验收，
当前profile显式直接GNU ld。来源/失败/输出完整哈希与命令见
[0020](../work_log/0020_seed_integration.md)，使用见[说明](../e08_gcc_seed.md)。
本页此前not_run是从端交付时状态，不再是主端C gate当前结论。
下一交付应为G++/cc1plus和真正target libstdc++/libsupc++（异常/RTTI/TLS基线），
不能把现有no-exceptions/no-rtti host闭包当目标库；ABI manifest接口见
[e08_cpp_abi_handoff.md](e08_cpp_abi_handoff.md)。E08-5尚未运行。
