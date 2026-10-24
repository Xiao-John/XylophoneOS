# E08-5 从端交接

状态：**A 已交付（target C++ runtime）；B 已构建（g++/cc1plus）；
A 的 6 个 ABI 探针 built_not_run；无 E08-5 客体 gate**。
本页是唯一共享输出入口。不修改原 C Seed、SDK 快照、共享 build/tests/state。

## A：target application C++ runtime

- 私有前缀：`.cache/xos_seed/gcc/e08_5/target_runtime/prefix`
- SDK 输入：`.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490`
  （manifest SHA256 同目录名，v4）。
- 源码：GCC 16.2.0 `libstdc++-v3`；host/target 均为 `x86_64-elf` 交叉，
  `--with-newlib --disable-shared --enable-static`。
- 关键 flags：`-fexceptions -frtti -ftls-model=local-exec -mno-red-zone`；
  **不是** host 的 `-fno-exceptions/-fno-rtti` 闭包。
- `libstdc++.a`：6.3 MiB，199 members，SHA256
  `8bba188c15fefbdad794816cca8544864f87033a2939011bb7763023b1e6e9ec`。
- `libsupc++.a`：357 KiB，SHA256
  `174948f1b8025b1ae195ae28d1196f86dd3bf5ea9e491d0b6220bc447570144a`
  （与 host 同名库不同，不能混用）。
- `libgcc.a`：1.7 MiB，SHA256
  `1d1755feabef4fbe34527df8f94f44e67f3fc2ce3b1d58dbf824ec858c994dfa`，
  来自真实 x86_64-elf cross libgcc，含 `_Unwind_RaiseException`/`_Unwind_Resume`。
- headers：`include/c++/16.2.0`，target config 在
  `include/c++/16.2.0/x86_64-unknown-elf/bits/c++config.h`。
- runtime manifest：`.cache/xos_seed/gcc/e08_5/target_runtime/prefix/manifest.json`，
  稳定副本 `src/ports/gcc/e08_5_target_runtime_manifest.json`，SHA256
  `538baa523869bda07455c79c0d406a69bfbc8442469d96a5b28e2741df9c689e`；schema 1，
  `runtime_kind=target_application_runtime`，6 个 feature 均声明 ready。
- C++23 `std`/`std.compat` modules 与当前交叉编译器不兼容，已跳过
  `libmodulesconvenience`；这是 host/target 构建裁剪，不是 ABI 失败，也不影响
  异常/RTTI/TLS/容器。
- `dirent` 只有 `DT_UNKNOWN/DIR/REG`，构建使用私有
  `src/ports/gcc/include/xos_dirent_compat.h` 补齐常量；不声称 XOS 有
  special files/symlinks。

### ABI 探针（宿主交叉构建，未客体执行）

命令：

```sh
python3 scripts/build_cpp_abi_probe.py \
  --sdk .cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490 \
  --runtime-prefix .cache/xos_seed/gcc/e08_5/target_runtime/prefix \
  --runtime-manifest .cache/xos_seed/gcc/e08_5/target_runtime/prefix/manifest.json \
  --output-root .cache/xos_seed/gcc/e08_5/abi_build \
  --features string_vector,exceptions,rtti,local_static,tls_destructors,multi_tu
```

结果：**BUILT_NOT_RUN**，6/6 feature 均为 `built_not_run`，15 条真实
compile/link 命令；不是客体通过。报告：
`.cache/xos_seed/gcc/e08_5/abi_build/cpp_abi_build_report.json`。

ELF 产物（均静态 x86-64、无 dynamic section）：

| feature | SHA256 |
|---|---|
| string_vector | `9c401d29494b22116200140b4137c55e74fbbd7ea7e0bda9d425499b440a51b8` |
| exceptions | `a54e619f5ef055944a73beed7a57656baafc5355fbe664f5099c91b3bf88bb9a` |
| rtti | `3bc92cefa54012747787b5152f131dbab8ab7b170e28e277f271594cdfde8d5c` |
| local_static | `52798fdf66018f5da75bf9c8a67bda791a897b5948f528adbd7a9a84a19a392f` |
| tls_destructors | `2ab3ffc99e273fc920e624fed0261bb3de2e2345e884e0993e1b42dfac1ccdca` |
| multi_tu | `89229d72c5e6172c2920ce571fdd6e5806a0a32e53ecbd77ee0e1ca6aa52b729` |

这些是 **早期 ABI 探针**，不是原生 G++ gate；只有主端客体执行才能把
feature 记为 passed/failed。

## B：g++/cc1plus（已构建，built_not_run）

- 独立工作目录：`.cache/xos_seed/gcc/e08_5/gxx`；新 source 副本，仅应用
  lstat/fixincludes/SARIF/no-truncate 平台补丁，**未套用** C-only 删除
  libcody/c++tools/utility 的补丁。
- host C++ 运行库使用 `.cache/xos_seed/gcc/stdcxx/prefix`（fno-exceptions/rtti，
  仅供编译器自身）；target A 库不在 B 构建中降级。
- `--enable-languages=c,c++`，`--with-newlib --disable-libstdcxx`（目标库由 A
  独立交付）；`all-gcc` 成功，`cc1plus` 自检完成。
- 安装（私有）：`.cache/xos_seed/gcc/e08_5/gxx/install`
  - `/usr/bin/x86_64-elf-g++` 3.83 MiB，SHA256
    `5a502b29643cf72b436518321c0717a39e2802b94bc6ef4bb5add3d36acb5c3f`
  - `/usr/libexec/gcc/x86_64-elf/16.2.0/cc1plus` 50.5 MiB，SHA256
    `bf41329947ee7715d35a26e6ffefb301afa1251d2e6ca54f8b5b78be1a5858ac`
  - `gcc`/`cc1`/`collect2` 同时安装；均静态 ELF64、无 dynamic section。
- manifest：`.cache/xos_seed/gcc/e08_5/gxx/manifest.json`，稳定副本
  `src/ports/gcc/e08_5_gxx_manifest.json`；163 项 install_files，tools 含
  `g++`/`cc1plus`/`gcc`/`cc1`/`collect2`；SHA256
  `ddc22e04954c68d871d4ed70adb7c224de2d8bf2d1213aa4e3a49b5433964e88`。
- ABI 构建报告 SHA256 `65f46bb55aaca35007daa185607b4450b37495dc11055a57e76a451c76133b30`。
- B **未客体运行**；没有原生 G++ gate。`collect2` 已随安装但未验收，默认
  g++ 链接是否走 collect2 需主端实测；E08-4 仍保持直接 GNU ld profile。
- C++23 `std`/`std.compat` modules 与当前交叉编译器不兼容，B/A 都跳过
  `libmodulesconvenience`；不影响异常/RTTI/TLS/容器构建。

## 边界与下一步

- 安装建议：A 的 `include/c++` → `/usr/include/c++`，`libstdc++.a`/
  `libsupc++.a` → `/usr/lib`；B 的 `g++`/`gcc` → `/usr/bin`，`cc1plus`/
  `cc1`/`collect2` → `/usr/libexec/gcc/x86_64-elf/16.2.0`。SDK CRT/libc/
  libxos/libgcc 仍按 v4 sysroot 安装。
- 主端先跑 `tests/cpp_abi_smoke.py --run-guest` 的 6 个早期 ABI 探针；
  全部客体执行通过后，再跑原生 g++ smoke。B 的 `g++` 驱动默认链接路径
  （是否 collect2）尚未验收，不能把 built_not_run 写成 E08-5 通过。
- 未运行 QEMU/客体；未修改原 C Seed/SDK/build/tests/state。
- 主端可用 A 的 manifest 立即做早期 ABI 构建/客体探针；正式 E08-5 仍需 B 的
  原生 G++ 设施 gate。
- B 完成后补 `install_files`/`guest_path`/哈希和许可材料，再交主端。

## 主端0022验收补记

A/B已接收并验收：六项ABI、原生G++4组/14命令及C++编辑/重启增量通过。
正文supc++哈希为旧值，采用实际文件且匹配B manifest的b8564d4b…；原始清单
保留作来源。实际修复旧TLS回退与v5入口重复定义，以及B g++的lrealpath漏返回。
独立派生目录与完整哈希/命令见../work_log/0022_cpp_seed_acceptance.md及
../e08_cpp_seed.md；综合结论e08_acceptance.md。原工具/库不就地改，collect2未
验收，当前固定静态GNU ld。后续正式重建应纳入0007并让target库正确探测v5的
TLS入口，避免再引入已修复问题；本轮没有重跑完整GNU构建。
