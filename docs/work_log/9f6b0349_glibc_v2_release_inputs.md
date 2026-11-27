# 9f6b0349 · glibc v2 发行输入重建

以主线 `8e66789c` 重建普通镜像和 glibc stock 安装器。镜像 build ID 为
`ce681c073de3d6c4`。dash、原生 xypm、daily、GNU Make 4.4.1、CPython
3.14.9 / zlib 1.3.2 和 IDNA 3.20 绑定
`xos-x86_64-glibc-unified-cxx-v2`。按 GNU Seed 的现有规则保留冻结的
GCC/G++、Binutils 及其对应源码，把 v2 sysroot 装入新工作盘。
[统一 v2 SDK](ee216d1d_glibc_file_network_unified_sdk.md) · [v1 发行证据](e2803194_glibc_gnu_seed_release.md)

CPython 上游配置仅用几个 socket 基础头探测 `_socket`，v2 SDK 缺少
`netinet/tcp.h`、`arpa/inet.h` 和 `netdb.h`，并在清单中把
`socket` 等接口登记为占位符。首次构建在编译 `socketmodule.c` 时失败。
glibc 构建入口核对所选 SDK 的必要头文件和占位符清单，使用 CPython 的
`n/a` 机制处理不满足条件的 SDK，并在构建回执登记当前 socket 适用范围。
重新配置和静态链接通过。交叉 `nm` 确认 `PyInit_zlib` 存在且
`PyInit__socket` 缺席。XPK 含 15 个受管文件与 558 成员标准库的归档。
[配置和 ELF 复核](../reports/glibc_release_unified_v2_20261127/cpython_configure_elf.json)

已验证的 v1 kit 连 `netinet/in.h` 也未提供，原配置将 `_socket` 标记为
`missing`。新探测在 v1 用 `n/a` 明确登记相同的模块缺席，保留已发布 v1
盘和回执。v1 和 v2 的 manifest 均登记 `accept`、`bind`、`connect`、
`listen`、`socket` 为占位符。
[两组 SDK 接口复核](../reports/glibc_release_unified_v2_20261127/socket_profile_comparison.json)

用 v1 kit 与已核签的 OpenSSL 3.5.9 复跑 CPython configure，得到
`_socket=n/a`、`_hashlib=yes`、`_ssl=missing`。本轮 v1 复核覆盖
配置，历史 hashlib 客体资格依然绑定原工件。
[v1 配置复验](../reports/glibc_release_unified_v2_20261127/v1_openssl_configure.json) ·
[既有客体](c1c3d3d7_cpython_static_openssl_hashlib.md)

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
- 同一发行工作盘的副本通过安装器和普通客体运行 CPython 线程、JSON、gzip、
  DEFLATE ZIP 与 IDNA，拒绝 v1 的 IDNA XPK。移除 daily 和 IDNA 后，
  15 个 CPython 受管文件及用户数据保留，另逐一核对 1,376 个 GNU Seed 文件。
  [包组合客体](../reports/glibc_release_unified_v2_20261127/package_guest.json) ·
  [Seed 回收后读回](../reports/glibc_release_unified_v2_20261127/seed_after_package_removal.json)
- 同初盘的另一份副本通过 20 项原生测试。直接用 GCC/G++ 编译链接并运行 C/C++，
  从 Xshell 和 dash 分别驱动 GNU Make，验证未定义符号拒绝，重启后复跑编译产物
  和 Python 发行脚本。两份链接图均使用 v2 sysroot，57 个受管文件逐项保持一致，
  各步骤资源回到 `129806 / 2 / 0`。
  [组合验收](../reports/glibc_release_unified_v2_20261127/combined_guest.json)

默认切换仍依赖完整静态重链接材料、升级与中断恢复，以及与更新主线产品、
数据盘的组合门。[发行验收表](../releases/glibc_default_gate.md)

候选按构建时的主线 `8e66789c` 固定。随后主线 `6580fc1e` 合入
[#345](https://github.com/Xiao-John/XylophoneOS/pull/345)，其差异在 Mobius
构建、打包、测试和报告。更新主线与 Mobius 进入同一工作盘时独立组合验证。

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
