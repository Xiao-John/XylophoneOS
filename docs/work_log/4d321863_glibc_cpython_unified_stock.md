# 4d321863 · 统一 glibc SDK 的 CPython stock 生命周期

用主线 `8d1b985d` 的构建与打包入口、统一静态 C/C++ SDK 和锁定的 CPython 3.14.9 源归档，重建解释器与 XPK。SDK profile 为 `xos-x86_64-glibc-unified-cxx-v1`，profile 摘要 `97385873…`，SDK manifest `b21c8b63…`。首套普通与 stock 安装候选从 `4964dfa5` 重建。#320 与 #321 合入后，再从主线 `643d9de2` 加验收提交 `4d321863` 重建两张 ISO 并复验。两组系统 manifest 分别绑定实际源码。期间 CPython 构建入口、端口、包格式及已绑定 SDK 的输入逐项相同，两组客体使用同一份 CPython ELF 和 XPK。

宿主复用由同一锁定源码构建、重新按摘要核验的 Linux arm64 Python 3.14.9，仅用于构建生成器。第一次实际编译在 GNU ar 生成 `libpython3.14.a` 时返回 ENOSPC，诊断时共享 Linux 构建卷剩 0 B。失败卷、源码回执和生成日志分别保留。另在与原卷隔离、大小写敏感的临时宿主磁盘从源归档重新交叉编译。成品遵循既有静态 TLS 与无动态扩展加载配置，三个 LOAD 段。XPK 中 ELF 剥离调试节后仍保留对应原 ELF、剥离器和程序头匹配回执。
[真实构建清单](../reports/glibc_cpython_unified_stock_20261127/build.json)
[首次归档失败](../reports/glibc_cpython_unified_stock_20261127/initial_storage_failure.json)

## 与旧构建的逐项对照

| 工件 | 旧 stock fork | 统一 SDK |
| --- | ---: | ---: |
| XPK 字节数 | 20,305,920 | 20,316,160 |
| 受管理文件数 | 14 | 14 |
| payload 字节数 | 20,287,605 | 20,292,566 |
| 包内 ELF 字节数 | 9,402,160 | 9,407,120 |
| 磁盘标准库 ZIP 字节数 | 10,654,445 | 10,654,445 |

两份包的文件路径与父目录逐项一致，558 个成员的标准库 ZIP 摘要同为 `2eb1eb04…`。本轮使用旧 XPK `a82ad13a…` 作为真实对照，新 XPK 为 `7314b376…`。
[逐文件摘要与许可清单](../reports/glibc_cpython_unified_stock_20261127/comparison.json)
[旧 stock fork 证据](bbf38ffb_cpython_stock_glibc_guest.md)

## 两套 QEMU 客体验收

| 系统 | 源码 | 普通解释器 | stock XPK 生命周期 |
| --- | --- | --- | --- |
| `add02bc4570ea44a` | `4964dfa5` | CPython 3.14.9 启动、时钟和线程通过 | 8 项通过 |
| `8a36d456821db893` | `4d321863` | 同一 ELF 冷启复验通过 | 8 项通过 |

两次都由真实安装 ISO 从空盘自动安装 dash、xypm 和 26 个受管日用文件。之后使用普通 ISO 冷启。原生 xypm 拒绝旧 stock fork 同名 XPK，恢复程序确认无事务。数据库、索引和用户文件摘要保持一致，宿主另核验两个 glibc profile 的互拒及冻结 newlib 的拒绝。

普通安装因缺维护租约被拒绝，经维护安装后停机校验 14 个 CPython 文件。重启从盘运行解释器和 Python 标准库测试，覆盖 JSON、argparse、hashlib、pathlib、TOML、XML、stored ZIP、时钟和原生线程。缺失模块真实退出 1。卸载清除 CPython 受管文件与事务状态，保留 26 个 stock 文件。两轮保留的原用户文件、UTF‑8 文本和 ZIP 字节摘要分别一致。维护安装、拒绝、运行和卸载后均恢复普通客体的资源基线 `129806 / 2 / 0`。

在第二轮的已安装盘快照上，工作区默认 glibc 入口核对全部 40 个受管文件。切回注册的冻结 newlib 后，宿主工具按数据库的 profile 拒绝同一盘。快照在两个选择前后全盘摘要一致。
[第二轮普通解释器](../reports/glibc_cpython_unified_stock_20261127/cli_guest.json)
[第二轮 stock XPK 回执](../reports/glibc_cpython_unified_stock_20261127/native_guest.json)
[首轮回执](../reports/glibc_cpython_unified_stock_20261127/earlier_replay.json)
[工作区选择校验](../reports/glibc_cpython_unified_stock_20261127/workspace_profile.json)

## 复现入口

用 Linux arm64 容器、同一锁定交叉工具和隔离的大小写敏感构建目录。若复用已有宿主 Python，环境中的 `BUILD_PYTHON` 应指向与目标版本一致且已核摘要的解释器。两个客体入口消费同一套工件，旧 XPK 和 profile 使用原始只读副本。stock 运行器在输出目录保留 stock 盘、CPython 安装后盘和卸载后盘。

```sh
candidate=build/candidates/cpython-unified-stock
python3 scripts/build_cpython.py --build-python "$BUILD_PYTHON" --archive "$CPYTHON_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --glibc-profile "$UNIFIED_KIT/profile.json" \
  --output-dir "$CPYTHON_BUILD" --compile-probe
python3 scripts/package_cpython_glibc.py --cpython-build "$CPYTHON_BUILD" --archive "$CPYTHON_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" --output "$CPYTHON_XPK"
python3 scripts/build_candidate.py --output "$candidate" --glibc-app-kit "$UNIFIED_KIT" \
  --glibc-daily-source "$SBASE"
python3 tests/cpython_glibc_guest.py --system-build "$candidate/system" --cpython-build "$CPYTHON_BUILD" \
  --archive "$CPYTHON_ARCHIVE" --sdk "$UNIFIED_KIT/sdk" --glibc-profile "$UNIFIED_KIT/profile.json" \
  --output build/unified-cpython/cli
python3 tests/cpython_glibc_xpk_guest.py --system-build "$candidate/system" --stock-candidate "$candidate" \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" --package "$CPYTHON_XPK" \
  --cpython-build "$CPYTHON_BUILD" --xypm-build "$candidate/stock/xypm.json" \
  --previous-package "$PREVIOUS_CPYTHON_XPK" --previous-profile "$PREVIOUS_PROFILE" \
  --maintenance-timeout 1200 --output build/unified-cpython/stock
```

## 发行边界

本批覆盖静态核心及本轮实际运行的标准库子集。生成的 Makefile 将 `_ssl`、
OpenSSL `_hashlib` 和 `zlib` 标为 `missing`。本轮实际运行的 `hashlib` 使用内置
摘要，ELF 的静态 TLS 是线程局部存储。SSL、HTTPS、zlib/gzip/压缩 ZIP、IDNA wheel、
额外静态扩展、交互式 REPL 和动态扩展加载分别保留资格边界。
[构建配置与模块范围](../reports/glibc_cpython_unified_stock_20261127/module_scope.json)

交付基线 `f09f2f7f` 包含 #311、#323 和 #324 的 D1 动态装载、普通组合回执与
ClarkE HTTPS。CPython 源、构建和打包入口与本轮比较结果一致。镜像与静态 SDK
沿用各自实际构建回执。发行默认及 newlib 退役由最终资产组合的真实构建、介质
验收和许可材料决定。
[默认发行验收表](../releases/glibc_default_gate.md)
