# ee216d1d · glibc C/C++ SDK 文件与网络地址合成

工作树从主线 `9dccbf3fd3fdab599320389d9b89be67c72f9e08` 构建，包含文件回复
等待 #339、Qt Quick #333 和网络地址 #340。起初从 #339 的实际合并提交与 #340
精确 head 生成候选树。#340 合并后，逐项将已启动的静态 C SDK 的 340 项构建输入
与最终 Git 树比较，摘要完全一致。GCC 配方和消费方夹具也逐字对照。普通和 Files
故障镜像直接从最终主线重建。

## 构建与范围

使用 `xos-x86_64-glibc-unified-cxx-v2` 作为单独候选。glibc 2.44 和上游 GCC 16.2.0
归档分别验签后构建。以同一次构建的 glibc C sysroot 配置并编译 POSIX
`libstdc++.a`、`libsupc++.a` 和五个展开相关对象，沿用已验的 POSIX 线程及 ABI
配方。发行、Qt 或 ClarkE 消费同一解包目录中的 `sdk` 和 `profile.json`。原 v1
候选及其既有安装盘继续使用原来的工件绑定。
工作区选择器继续按已注册的工具包和回退配置工作，本轮 v2 通过显式参数使用。当前
默认发行仍沿用原 newlib 配方。
[工作区选择与回退](50e9a5a4_glibc_sdk_default.md) · [默认发行验收](../releases/glibc_default_gate.md)。

验收使用当前仓库的 [统一 SDK 入口](5ffb8e82_glibc_cxx_sdk.md)，以及独立的文件等待
和网络地址探针。出站 socket、CPython SSL、动态加载及 Qt/ClarkE 自身完整重编
各走专项门。

## 结果与工件

`build/unified/xos-glibc-unified-cxx-v2.tar.gz` 为 19,835,278 字节。解包到
`build/unified/relocated/application-sdk` 后与原组装目录逐项一致。两套签名材料和
运行库许可文本通过工件摘要核验。`build/unified/rollback/v1` 保留可搬移的 v1 回退。
v1/v2 的 C++ ABI 和 gthreads 宏一致，五个静态库的既有全局定义全部保留。互换
profile 和 SDK 的两种组合均被拒绝，v1 也拒绝 v2 的 C++ XPK。
[源码、签名及工件绑定](../reports/glibc_file_network_unified_20261127/binding.json) ·
[静态 ABI 差分](../reports/glibc_file_network_unified_20261127/abi.json)。

普通系统 `1958db24f4ad591d` 通过 11 项统一客体检查，覆盖 C 路径、C++ 全局构造、
线程与 TLS、实际异常展开、Dash 和 xypm。网络门额外运行 C11、C++20 及 newlib
对照三项，核对 IPv4、IPv6 地址对象、字节序和 Net2 v2 线上表示。普通文件门在
xsh 与 Dash 验证读就绪、期限、并发读及取消，共五项。故障系统 `a33f6cfa96bdd297`
分别验证真实 Files 停机后的对端唤醒和 glibc 的公开 EIO，工具包与普通系统相同。
[组合客体回执](../reports/glibc_file_network_unified_20261127/guest.json)。

第一次独立工程运行时，容器镜像预置的空 `/repo` 触发隔离前置检查。换用相同目标
工具、根目录没有该路径的镜像后，C 与 C++ 均完成构建、检查和打包。文件探针的首次
链接准备缺少内部头目录，复跑从搬移工具包内绑定的 `usr/share/xos-glibc/port/sysdeps/xos`
读取相关源头。两次失败各留在独立构建日志中。

## 复现入口

在断网 Linux 容器内沿用签名源码和锁定交叉工具。GCC 源归档、独立签名和审核过的
密钥放入 `build/unified/cxx/material`。`V1_KIT` 指向已经验过绑定的旧工具包。

```sh
out=build/unified
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$out/sdk_c" --jobs 6
python3 tests/stage_glibc_unified_sdk_recipes.py --output "$out"
```

把 `$out/cxx` 挂载到容器的 `/work`，把本次 `$out/sdk_c` 只读挂载到 `/work/sdk`。
依次执行 `material/prepare.sh`、`material/compile.sh` 和 `material/build_unwinder.sh`。
用与上一轮统一 SDK 相同的方式组装并搬移产物，候选 ID 使用 v2。

```sh
PYTHONPATH=scripts python3 "$out/assemble.py" "$V1_KIT/sdk"
python3 scripts/create_xypm_profile.py create --runtime-family glibc --sdk-build "$out/sdk_cxx" \
  --id xos-x86_64-glibc-unified-cxx-v2 --cxx --feature directories --feature threads \
  --feature stdio_transfer --output "$out/profile.json"
python3 scripts/package_glibc_sdk.py --sdk-build "$out/sdk_cxx" \
  --profile "$out/profile.json" --output "$out/application-sdk"
mkdir -p "$out/relocated" "$out/records"
(cd "$out" && tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - application-sdk \
  | gzip -n > xos-glibc-unified-cxx-v2.tar.gz)
tar -xzf "$out/xos-glibc-unified-cxx-v2.tar.gz" -C "$out/relocated"
python3 scripts/build.py --output-dir "$out/system-mainline" --quiet-demos-on-launch
python3 scripts/build.py --output-dir "$out/death-mainline" --quiet-demos-on-launch --glibc-files-death-probe
```

解包到不同目录后复用原独立工程构建法，C 和 C++ 工程都执行 `init`、`build`、
`check` 和 `pack`。在同一搬移工具包下重建 Dash、xypm 和文件等待探针，再以普通
镜像执行 C/C++、网络和文件门，以故障镜像执行真实 Files 停机门。

```sh
kit="$out/relocated/application-sdk"
python3 scripts/build_dash.py --sdk "$kit/sdk/sysroot" --glibc-profile "$kit/profile.json" \
  --receipt "$out/records/dash.json"
python3 scripts/build_xypm.py --sdk "$kit/sdk" --profile "$kit/profile.json" > "$out/records/xypm.json"
python3 scripts/build_glibc_program.py --sdk "$kit/sdk/sysroot" --profile "$kit/profile.json" \
  --include-dir "$kit/sdk/sysroot/usr/share/xos-glibc/port/sysdeps/xos" \
  --source tests/fixtures/glibc_g3/file_reply_wait_probe.c --output "$out/records/file_reply_wait.elf"
python3 tests/glibc_unified_sdk_guest.py --system "$out/system-mainline" --kit "$kit" \
  --consumer "$out/consumer" --dash-receipt "$out/records/dash.json" \
  --xypm-receipt "$out/records/xypm.json" --output "$out/guest-unified"
python3 tests/glibc_inet_addresses_guest.py --sdk "$kit/sdk" --profile "$kit/profile.json" \
  --system "$out/system-mainline" --system-source "$PWD" --output "$out/guest-inet"
dash=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["elf"])' "$out/records/dash.json")
python3 tests/glibc_file_reply_wait_guest.py --system "$out/system-mainline" --death-system "$out/death-mainline" \
  --sdk-manifest "$kit/sdk/manifest.json" --profile "$kit/profile.json" \
  --probe "$out/records/file_reply_wait.elf" --probe-receipt "$out/records/file_reply_wait.elf.build/manifest.json" \
  --dash "$dash" --dash-receipt "$out/records/dash.json" --output "$out/guest-files"
```
