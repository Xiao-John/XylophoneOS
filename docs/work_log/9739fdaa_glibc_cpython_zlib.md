# 9739fdaa · 统一 glibc SDK 的 CPython 静态 zlib

以 #325 实测提交 `5b40363e` 为基线。用其同一静态 C/C++ SDK、profile
`xos-x86_64-glibc-unified-cxx-v1` 和 3.14.9 CPython 源。从现有
`zlib_lock.json` 固定的 1.3.2 归档实际编出目标依赖。上游原 URL 返回 404，
旁路取到的三个镜像副本均符合锁中完全相同的 SHA-256。本次构建使用其中的
MacPorts 副本。[zlib 1.3.2 上游发布](https://github.com/madler/zlib/releases/tag/v1.3.2)
· [归档镜像](https://distfiles.macports.org/zlib/)

首次 zlib 构建中，原 configure 用裸交叉编译器进行链接探针，因缺少目标
`crt0.o` 误判 `strerror` 和 `vsnprintf`。首次重复归档的 SHA-256 也不同。
现仅在 glibc 路径让链接测试使用真实 XOS crt、链接脚本及静态 SDK 档案，在
探针源码后传入 `LIBS`，并显式用确定性 ar/ranlib 参数。最终两个独立目录产出
相同的两个头和 `libz.a`，15 个成员均为 x86-64 ELF。原 newlib 模式宿主交叉
归档仍可构建。

CPython 选项 `--zlib-prefix` 验证 zlib receipt 的源码、构建器、工具与 SDK
绑定，复制并核验实际输入后交给构建。输出仍是静态 TLS 解释器。包内仍使用
原 558 成员的 stored 标准库 ZIP。启用 zlib 的原生包为 3.14.9-1，带 zlib
源、许可和实际归档摘要。篡改头和错 SDK 均在创建 CPython 工作目录前拒绝。

一轮 CPython 尝试把已核摘要的宿主解释器挂在不同目录，找不到其原版标准库的
`encodings`。调整为宿主构建时的挂载路径并新建目标目录后从原归档重新编译。
早期 zlib 和 CPython 工件、受控中止的客体盘及失败记录均保留。

## 目标与客体验收

最终 `libz.a` 为 157,126 B，摘要 `8434b9b4…`。CPython ELF 含实际
`PyInit_zlib`、`deflate` 与 `inflate`，XPK 为 20,408,320 B、15 个受管文件，
摘要 `2c23731b…`。无 zlib 参数的静态核心路径仍配置成功且保持 `zlib` 缺失。

在普通系统 ISO `6f700746e7efd3d8` 上，独立 C 程序从该目标归档链接，实际执行
`gzopen`、有界 `gzprintf` 与 `gzread`，随后用宿主解压得到逐字节相同的文本。
原 CPython CLI 入口的启动、时钟和线程用例也通过。

完整原生 XPK 测试通过 8 项。旧 stock fork 与冻结 newlib 拒绝错 profile，交叉
拒绝后的恢复确认无事务。维护安装并停机核对 15 个文件，冷启运行磁盘标准库、
时钟与线程。实际脚本通过流式压缩、gzip 往返、DEFLATE ZIP、压缩模块导入、
坏流和 CRC 拒绝。卸载清除受管文件与事务，原用户文件、UTF‑8 文本、stored ZIP、
gzip 与 DEFLATE ZIP 由宿主停机读回并验证内容。正常原生门的资源基线为
`129806 / 2 / 0`。同一 profile 的 3.14.9-0→3.14.9-1 用宿主离线事务独立验证，
保留原盘全盘摘要及用户标记。

生成的解释器 Makefile 把 `zlib` 标为 `yes`，把 `_ssl` 与 OpenSSL
`_hashlib` 标为 `missing`。另用已安装快照的字节一致副本冷启，压缩脚本再次通过，
实际导入 `_ssl` 得到该模块缺失，原快照字节保持一致。ELF 静态 TLS 支持线程局部
存储，SSL/HTTPS、其他压缩模块和动态扩展继续各自验收。
[C 依赖](../reports/glibc_cpython_zlib_20261127/c_guest.json)
[原生生命周期](../reports/glibc_cpython_zlib_20261127/native_guest.json)
[SSL 范围](../reports/glibc_cpython_zlib_20261127/ssl_scope_guest.json)
[证据索引](../reports/glibc_cpython_zlib_20261127/manifest.json)

## 发行组装的实测重叠

用锁定的 IDNA 3.20 wheel 生成统一 profile 的真实 XPK，与 #325 产出的 daily
XPK 可由宿主 xypm 在同一新盘顺序离线安装并校验 42 个文件。给现行发行组装
入口同一 SDK、系统和两份 XPK，先命中 daily 与 wheel 的无条件互斥。去掉
wheel 后仍命中旧 profile 的发行系统白名单，绑定的 glibc SDK 使用另一种
manifest 表达。下一步需要发行装配从同一候选清单验证 profile 与完整工件，并
在最终介质验收实际导入 IDNA。工作区和发行默认按各自门禁。
[两份 XPK 和宿主合装回执](../reports/glibc_cpython_zlib_20261127/daily_wheel_assembly.json)

## 复现

```sh
python3 scripts/build_cpython_zlib.py --archive "$ZLIB_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --glibc-profile "$UNIFIED_KIT/profile.json" --output-dir "$ZLIB_BUILD"
python3 scripts/build_cpython.py --archive "$CPYTHON_ARCHIVE" --sdk "$UNIFIED_KIT/sdk" \
  --glibc-profile "$UNIFIED_KIT/profile.json" --zlib-prefix "$ZLIB_BUILD/prefix" \
  --output-dir "$CPYTHON_BUILD" --build-python "$BUILD_PYTHON" --compile-probe
python3 scripts/package_cpython_glibc.py --cpython-build "$CPYTHON_BUILD" --archive "$CPYTHON_ARCHIVE" \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" --output "$CPYTHON_XPK"
python3 scripts/build.py --quiet-demos-on-launch
python3 scripts/build_xypm.py --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" \
  > build/cpython-zlib-xypm.json
python3 tests/cpython_glibc_xpk_guest.py --system-build build --cpython-build "$CPYTHON_BUILD" \
  --sdk "$UNIFIED_KIT/sdk" --profile "$UNIFIED_KIT/profile.json" --package "$CPYTHON_XPK" \
  --xypm-build build/cpython-zlib-xypm.json --previous-package "$PREVIOUS_CPYTHON_XPK" \
  --previous-profile "$PREVIOUS_PROFILE" --keep-work-disk --maintenance-timeout 1200 \
  --output build/cpython-zlib-native
```

宿主 Python 需要与源锁同版本，并能找到自身标准库。用断网 Linux arm64 运行
交叉工具及 QEMU。CPython 源树需要大小写敏感的新构建目录。用户原有工作盘
与两个配方对照使用只读挂载，客体盘存放各自输出目录。

交付时与主线 `1086f41b` 核对。期间 #318 的额外运行时改动属于 shared C++，#328 为组合回执。
实测回执继续绑定本轮 `9739fdaa` 的构建源码、独立工作盘和封存的静态 SDK。
