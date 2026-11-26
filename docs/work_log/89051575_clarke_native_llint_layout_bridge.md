# 89051575 · ClarkE 原生 LLInt 布局生成

2026-11-26 · 从主线 `db8e15dd` 继续。XOS 目标选用实际 glibc 的 pthread 类型，
使 WPE WebKit 2.54.2 的两个上游提取器能使用同一组目标头和配置。仅解包 118 MiB
左右的 JSCOnly 构建输入。首次局部解包忽略 `unifdef` 与 gtest，补齐后配置通过。
`unifdef` 从锁定源码以宿主 C 编译器生成，CMake 配置使用该宿主可执行文件。

Linux arm64 以 CMake 4.4.5、Ninja 1.13.2、Ruby 3.3.8、Python 3.14.10 和
目标 GCC/G++ 16.2.0、GNU binutils 2.47 构建。六个交叉工具的文件摘要均与已验签
glibc/GCC 源构建的 C/C++ SDK 清单相同。ICU 79.1 目标包及实际 `data`、`i18n`、
`uc` 三个库与此前已验签源构建和客体验证的输入一致。正式布局构建在断开容器网络后执行。

```sh
python3 scripts/create_xypm_profile.py create --runtime-family glibc --cxx \
  --sdk-build "$GLIBC_BUILD" --id xos-x86_64-glibc-clarke-llint \
  --output "$GLIBC_CXX_PROFILE"
python3 src/ports/webkit/build_llint_layout.py \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" \
  --output build/clarke_llint_layout
```

从 `e0d0c9f0` 复跑通过。容器限制为 1 GiB 和一个 CPU，Ninja 仅一个任务。先前
900 MiB 下，干净复跑的偏移提取器大翻译单元触发了 cgroup OOM，关闭优化的诊断也
触发同一限制。本轮保留上游 Release 配置，构建期间无新增 OOM 终止。复跑汇编与早先
探索构建逐字节一致。宿主 `unifdef` 是 AArch64 ELF。两个提取器都是 x86-64 静态
ELF，具备 LOAD 与 TLS 段，目标链接器保留了 libc 的 `raise` 和 `__getcwd` 警告。

原样运行上游生成命令。宿主 Ruby 读目标设置表并生成 `LLIntDesiredOffsets.h`，
再读第二个目标 ELF 的实际偏移数据，生成含 `vmEntryToJavaScript` 的原生汇编头。
核对了五个工件摘要。未执行目标 ELF、编译解释器汇编对象、链接 WTF/JSC shell 或运行
客体引擎。单 mutator 准入和跨线程根扫描仍由 [线程契约](../contracts/clarke_jsc_threading.md)
约束。

| 输入或工件 | SHA-256 |
| --- | --- |
| SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| SDK 树 | `2070dbad9ddd860a11dd1511f1268c1f62683df01d1a967bfa741e53df0799d6` |
| glibc C/C++ profile | `3aa343495c26d715460fed84480014ab505c1a6f92976a3c6eb617341ef6562c` |
| ICU 目标归档 | `d64f090773eb9027bf9e0d46c95c8a60ed6d0817429f516c3807c0554178acb4` |
| `LLIntSettingsExtractor` | `8e4771feb65926759e4e2c573226698f7e2e01605acb9d3963e1d3ea02cadab2` |
| `LLIntOffsetsExtractor` | `2604bfe415c58c4f8a89693e6f244e4ce4f51df4865c1dac8a07f480137e7d7b` |
| `LLIntDesiredSettings.h` | `9e2e5f2567fe101217a67f3f6ec64e535fd3aca9663dff18804df91f7226c504` |
| `LLIntDesiredOffsets.h` | `0223b74b5699612177f2f945c09a2ea02257a658c64ea3561b601c3004dc610b` |
| `LLIntAssembly.h` | `80a43439e2d8eded82168096dbfe8067c0e24b429e8dfe9e782ebac0ed9d6ee9` |
| `build/clarke-llint-final/manifest.json` | `de0fe93c3c6af43a648612415a5e8b253c8e4221583008f96371cff215a5a3da` |
| `build/clarke-llint-final/configure.log` | `f78d6a3514dcd59df3906b19539437f586668168e181958401dd9d369850c521` |
| `build/clarke-llint-final/layout.log` | `fa16bc16bbcbcfbe82840285c09a12daa3112a532c855355bd9f5592fcddef2f` |
