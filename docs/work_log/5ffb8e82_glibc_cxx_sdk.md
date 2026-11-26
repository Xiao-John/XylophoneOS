# 5ffb8e82 · 统一 glibc C/C++ SDK 静态验收

基于 `af47b2c5` 的当前 glibc C 运行库源码和 #306 补齐的终端头库存，在独立目录从已验签的 glibc 2.44 归档重建 C SDK。用同一次构建的 sysroot、启动对象和终端归档，重新配置并编译已验签 GCC 16.2.0 的 POSIX `libstdc++.a`、`libsupc++.a` 和 C++ 头文件。五个 DWARF2/SJLJ 展开、帧注册、C personality 和 emutls 对象也从同一 GCC 源和 C sysroot 重编译，装回这次 C SDK 的 `libgcc.a`。其余 `libgcc.a` 对象逐字节保持原有工具链对象。两个容器使用的八个交叉工具摘要一致。

新的候选 ID 为 `xos-x86_64-glibc-unified-cxx-v1`。profile 声明 C++、目录、POSIX 线程与 stdio transfer，仍采用静态 ELF 和原生 TLS。profile 核验对完全一致的 sysroot 文件集合、两套来源验签、所有归档成员格式、CRT、展开器的强 pthread 引用和编译工具做绑定。与冻结的 stock 和 ClarkE 比对，两个旧 SDK 的五库全局定义均被保留，C++11 ABI、dual ABI、inline version 与 POSIX gthreads 宏一致。新 `libc.a` 包括 `faccessat`、`__faccessat`、`readlink` 与 `realpath`，libstdc++ 检测启用了 `_GLIBCXX_USE_REALPATH`。

| SDK | Manifest SHA-256 | Profile SHA-256 |
| --- | --- | --- |
| 统一 C/C++ | `b21c8b6388d85a66845c815e486e7f94f21099f914367827d684715f272a892f` | `97385873d525a3b8870b21a2e57cf04a7b357061bbc17f15edda65b9a842cb0c` |
| 冻结 stock | `d32a5c3b604016492df6af8ca04445b8d050cc81d4225db68cf4926e17c6aa7b` | `a7bf0f845819b1deae2939991144e8feba03a335362e5fbee24c88f71dbe3b25` |
| 冻结 ClarkE LLInt | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` | `3aa343495c26d715460fed84480014ab505c1a6f92976a3c6eb617341ef6562c` |

本地 `build/unified/rollback/stock` 和 `build/unified/rollback/browser` 保留两套原 SDK 和 profile 的可搬移副本。两套回退分别通过完整绑定核验。新旧 profile 互换 SDK 的四项检查均拒绝，新 C++ XPK 也分别被两套旧 profile 拒绝。既有工作盘继续使用其原 profile。

## 搬移与客体

以 `package_glibc_sdk.py` 组装 SDK，归档 `xos-glibc-unified-cxx-sdk.tar.gz` 为 19,813,481 字节，SHA-256 为 `c136383acc64a4275401ce6ff8192636d1c06a1d6951da593badb15f29b1b607`。归档整体解包到不同路径，目录树与组装结果完全一致。在未挂载仓库的断网 Linux arm64 容器中只挂载搬移后的 SDK 和用户工程，C 与 C++ 外部项目均完成 `init`、`build`、`check` 和 `pack`，配套交叉工具仍由环境提供。

从 `af47b2c5` 构建的普通客体镜像 `87aaa022d9b21c60` 在 QEMU 11.1.3 通过 11 项。Xsh 和用同 SDK 重建的 glibc dash 各三次执行构造和路径样例。C++ 运行核对全局构造、主线程 TLS 析构、两个工作线程的独立 TLS、析构计数、实际异常展开和 ClarkE `query_stack_bounds`。C 样例覆盖 UTF-8 路径、相对和绝对路径、`faccessat`、`readlink`、正规化和失败语义。Xsh 还运行同 SDK 构建的 stock xypm 0.4.0。五个 ELF 的 FAT 读回摘要一致，每次检查后资源恢复到 `129806 / 2 / 0`。只用于设置 FAT 只读属性的辅助程序由系统自身 SDK 构建。

首次宿主运行更正了 SDK manifest 字段的读取位置。首次有客体的尝试用 `exec-file` 启动 dash，按 Xsh 权限策略收到创建子进程的拒绝。最终复跑沿用普通 Xsh 命令启动，其原有的进程创建权限仍由系统决定。两次错误分别留存，避免将启动方式错误归因于新运行库。宿主 profile 回归通过 45 项。

## 复现入口

以下目录与命令以仓库根为起点。使用已锁定的 Linux arm64 交叉工具镜像。`GLIBC_ARCHIVE` 指向签名的 glibc 源归档。`FROZEN_STOCK` 和 `FROZEN_BROWSER` 指向上表已核验的完整工具包。

```sh
out=build/unified
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$out/sdk_c" --jobs 4
python3 tests/stage_glibc_unified_sdk_recipes.py --output "$out"
```

将 `gcc-16.2.0.tar.xz`、同名 `.sig` 和锁定 `gnu-keyring.gpg` 放入 `$out/cxx/material`。断网容器中将 `$out/cxx` 挂载到 `/work`。运行 `/work/material/prepare.sh` 验签并展开，随后把本次 `$out/sdk_c` 只读挂载到 `/work/sdk`，分别运行 `/work/material/compile.sh` 和 `/work/material/build_unwinder.sh`。

```sh
PYTHONPATH=scripts python3 "$out/assemble.py" "$FROZEN_STOCK/sdk"
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build "$out/sdk_cxx" --id xos-x86_64-glibc-unified-cxx-v1 --cxx \
  --feature directories --feature threads --feature stdio_transfer --output "$out/profile.json"
python3 scripts/package_glibc_sdk.py --sdk-build "$out/sdk_cxx" \
  --profile "$out/profile.json" --output "$out/application-sdk"
python3 scripts/build.py --output-dir "$out/system" --quiet-demos-on-launch
mkdir -p "$out/relocated" "$out/rollback" "$out/records"
cp -R "$FROZEN_STOCK" "$out/rollback/stock"
cp -R "$FROZEN_BROWSER" "$out/rollback/browser"
(cd "$out" && tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - application-sdk \
  | gzip -n > xos-glibc-unified-cxx-sdk.tar.gz)
tar -xzf "$out/xos-glibc-unified-cxx-sdk.tar.gz" -C "$out/relocated"
```

按证据中的 `build_detached_consumer.sh` 在另一路径构建消费者。把已解包的工具链和工程分别挂载到 `/kit/glibc`、`/apps`。源码目录包含 `tests/fixtures/glibc_g3/{cwd_probe.c,unified_cpp_probe.cpp}` 与 `src/ports/webkit/threading/xos_stack_bounds.{cpp,hpp}` 四个文件。

```sh
kit="$out/relocated/application-sdk"
python3 scripts/build_dash.py --sdk "$kit/sdk/sysroot" --glibc-profile "$kit/profile.json" \
  --receipt "$out/records/dash.json"
python3 scripts/build_xypm.py --sdk "$kit/sdk" --profile "$kit/profile.json" > "$out/records/xypm-build.json"
python3 tests/glibc_unified_sdk_guest.py --system "$out/system" --kit "$kit" \
  --consumer "$out/consumer" --dash-receipt "$out/records/dash.json" \
  --xypm-receipt "$out/records/xypm-build.json" --output "$out/guest-new"
```

初次本地交付基线 `fe981f72` 增加此前 xypm 跨版本验收，相关运行源码和 SDK 输入没有变化。本轮资格覆盖静态 SDK、stock 使用的 dash/xypm 入口以及 ClarkE 的原生栈边界。完整浏览器、存量包批量重建和默认 SDK 切换仍由各自的验收门决定。
[来源、ABI 与客体证据](../reports/glibc_unified_sdk_20261127/manifest.json) · [早期 C/C++ 配方](5a828b33_glibc_stock_fork_sdk.md)

## #310 和 #305 后的主线对照

#310 在 `adfa477e` 合入 Qt Quick 发行材料清单和校验脚本。静态候选的系统、glibc 与应用构建输入相同。#305 合入 `aece9965`，固定动态解释器的启动路径，其新增控制台输出和配套编译标志由 `SHARED && IS_IN (rtld)` 或解释器专属 `.os` 进入。共用 `xos_console.h` 提取了现有终端错误映射。单独解包与该合入提交树逐字节对应的快照，再从已验签源码实际重建静态 C SDK。338 个已安装 C 头逐文件一致，四份静态归档的成员名和全局定义集合一致，个别归档原始字节摘要有变化。

从新主线运行输入重建普通镜像 `5e426385002fc2f2`。QEMU 上，新 C 库通过四项实际 G2 构造、退出和错误输出，并通过系统自身的 newlib 对照。冻结的统一 C/C++ 原套件和原应用字节在同一新镜像重新通过 11 项客体组合，仍绑定 `97385873…`。这组独立复验覆盖静态 SDK 与普通镜像，动态解释器本身沿 #305 的专项资格。
[合入后静态对照](../reports/glibc_unified_sdk_20261127/post305_static.json)
