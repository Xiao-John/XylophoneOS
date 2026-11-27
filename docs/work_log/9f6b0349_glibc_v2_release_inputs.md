# 9f6b0349 · glibc v2 发行输入重建

以主线 `8e66789c` 重建普通镜像和 glibc stock 安装器。镜像 build ID 为
`ce681c073de3d6c4`。dash、原生 xypm、daily、GNU Make 4.4.1、CPython
3.14.9 / zlib 1.3.2 和 IDNA 3.20 绑定
`xos-x86_64-glibc-unified-cxx-v2`。按 GNU Seed 的现有规则保留冻结的
GCC/G++、Binutils 及其对应源码，把 v2 sysroot 装入新工作盘。
[统一 v2 SDK](d6ead81f_glibc_profile.md) · [v1 发行证据](e2803194_glibc_gnu_seed_release.md)

CPython 上游配置仅用几个 socket 基础头探测 `_socket`，v2 SDK 缺少
`netinet/tcp.h`、`arpa/inet.h` 和 `netdb.h`，并在清单中把
`socket` 等接口登记为占位符。首次构建在编译 `socketmodule.c` 时失败。
glibc 构建入口核对所选 SDK 的必要头文件和占位符清单，使用 CPython 的
`n/a` 机制处理不满足条件的 SDK，并在构建回执登记当前 socket 适用范围。
重新配置和静态链接通过。交叉 `nm` 确认 `PyInit_zlib` 存在且
`PyInit__socket` 缺席。XPK 含 15 个受管文件与 558 成员标准库的归档。
[配置和 ELF 复核](../reports/glibc_release_unified_v2_20261127/cpython_configure_elf.json)

## 验证

- 用同一份锁定的 glibc v2 kit 在隔离的 Linux arm64 宿主重建，目标 x86-64。
  QEMU TCG 从真实安装 ISO 启动，自动安装 daily 后冷启普通 ISO，运行 13 个命令，
  卸载并读回原用户文件与命令产出。安装与普通会话的资源分别回到
  `125920 / 2 / 0` 和 `129806 / 2 / 0`。
  [stock 客体与串口](../reports/glibc_release_unified_v2_20261127/manifest.json)
- 显式发行入口组装同时包含 v2 SDK、GNU Seed、daily、CPython/zlib 与 IDNA 的盘。
  工作盘有 57 个 XPK 受管文件、1,376 个 GNU Seed 文件及对应的四份归档。
  发行清单 SHA-256 为
  `b2b417bdf2fed26d02d22786cf1ed39fa5036324a6b6514bab3e89fdfefd82ef`。
  [工件绑定](../reports/glibc_release_unified_v2_20261127/binding.json) ·
  [发行摘要](../reports/glibc_release_unified_v2_20261127/release.json)
- 接收方在断网 Linux 环境中从四份归档重开，核对盘上受管文件与 GNU Make 签名。
  缺项、重复、内容不符和额外成员的归档被拒。
  [接收方验证](../reports/glibc_release_unified_v2_20261127/receiver.json)
- 发行工作盘的包回收与原生工具组合客体验收正在执行。默认切换仍依赖
  最终候选的可替换静态运行库、升级与中断恢复、
  应用组合和发布材料门。[发行验收表](../releases/glibc_default_gate.md)

## 复现

```sh
python3 scripts/build_candidate.py --output "$CANDIDATE" --glibc-app-kit "$KIT" \
  --glibc-daily-source "$SBASE" --installer-guest
python3 scripts/build_cpython_zlib.py --archive "$ZLIB_ARCHIVE" \
  --sdk "$KIT/sdk" --glibc-profile "$KIT/profile.json" --output-dir "$ZLIB_BUILD"
python3 scripts/build_cpython.py --archive "$PYTHON_ARCHIVE" \
  --sdk "$KIT/sdk" --glibc-profile "$KIT/profile.json" --zlib-prefix "$ZLIB_BUILD/prefix" \
  --build-python "$BUILD_PYTHON" --output-dir "$PYTHON_BUILD" --compile-probe
python3 scripts/package_cpython_glibc.py --cpython-build "$PYTHON_BUILD" \
  --archive "$PYTHON_ARCHIVE" --sdk "$KIT/sdk" --profile "$KIT/profile.json" --output "$CPYTHON"
python3 scripts/xypm_python_wheel.py "$IDNA_WHEEL" --profile "$KIT/profile.json" -o "$IDNA"
python3 scripts/build_gnu_make.py --archive "$GNU_MAKE_SOURCES/make-4.4.1.tar.gz" \
  --signature "$GNU_MAKE_SOURCES/make-4.4.1.tar.gz.sig" \
  --keyring "$GNU_MAKE_SOURCES/gnu-keyring.gpg" --sdk "$KIT/sdk" \
  --profile "$KIT/profile.json" --output-dir "$GNU_MAKE_BUILD"
scripts/release_pipeline.sh package --release-dir "$RELEASE" \
  --glibc-candidate "$CANDIDATE" --glibc-app-kit "$KIT" \
  --cpython-package "$CPYTHON" --wheel-package "$IDNA" \
  --gnu-seed-donor "$FROZEN_DONOR" --gnu-make-receipt "$GNU_MAKE_BUILD/manifest.json" \
  --gnu-make-sources "$GNU_MAKE_SOURCES"
python3 tests/glibc_gnu_seed_release_preflight.py --release "$RELEASE" --output "$HOST_REPORT"
scripts/release_pipeline.sh smoke --glibc-release "$RELEASE" --output "$GUEST_REPORT" \
  --foreign-package "$V1_IDNA"
```
