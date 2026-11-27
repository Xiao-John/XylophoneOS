# cf828683 · glibc v2 CPython/zlib 接收复验

断网 Linux 接收方从[补充归档](9c747f60_glibc_v2_component_sources.md)还原上游源码、
锁和实际构建脚本，使用冻结发行的只读 v2 SDK。重建的 157,126 字节 `libz.a`、
全部 15 个 x86-64 对象、两个头文件和构建回执与原件逐字节相同。实际发行 CPython
XPK 的内嵌回执及冻结 CLI 回执都绑定这套 zlib。

CPython 首轮重编的解释器加载字节有差异，558 个标准库成员一致。冻结 ELF 和
`Modules/getbuildinfo.o` 均含编译时间 2026-11-27 06:06:10 UTC。第二次构建使用
`SOURCE_DATE_EPOCH=1795759570` 和冻结回执记录的只读宿主 Python 3.14.9，完整 ELF
及正式打包产生的运行时 ELF 与原件逐字节相同，558 个标准库成员也全部相同。
两次均用正式 CLI 和 XPK 配方构建，工作区置于容量合计 880 MiB 的内存盘，并以
两颗 CPU 为上限。宿主 Python 已核对原构建摘要。

冻结 XPK 和第二次构建的 XPK 只在 `manifest.json` 与内嵌 `build_receipt.json`
两项有差异。新旧 CLI 回执只有 `steps` 变化，`target_make.log` 的 372 行内容与各行
计数相同，顺序不同。两份回执各自绑定本次原始日志。现有 XPK 的整包摘要仍无法从
这次复跑产物得到。接收方宿主 Python 从源码自举和新客体运行尚待验证。
[可公开复验回执](../reports/glibc_v2_cpython_receiver_20261127/manifest.json)

## 复跑冻结发行

先验证补充归档及其中 135 个输入。正式构建所用脚本和端口文件取归档中的
`xos/python`，将冻结 v2 工具、SDK 和两个上游归档置于接收方可读的位置。
`BUILD_PYTHON` 是冻结回执绑定的宿主 Python。比对完整 ELF 时沿用原回执所记
绝对构建路径，各输入摘要和期望产物摘要在复验回执中。

```sh
python3 -B scripts/build_cpython_zlib.py --archive "$ZLIB_ARCHIVE" --sdk "$KIT/sdk" \
  --glibc-profile "$KIT/profile.json" --output-dir "$ZLIB_BUILD"
SOURCE_DATE_EPOCH=1795759570 python3 -B scripts/build_cpython.py --archive "$PYTHON_ARCHIVE" \
  --sdk "$KIT/sdk" --glibc-profile "$KIT/profile.json" --zlib-prefix "$ZLIB_BUILD/prefix" \
  --build-python "$BUILD_PYTHON" --output-dir "$PYTHON_BUILD" --compile-probe
python3 -B scripts/package_cpython_glibc.py --cpython-build "$PYTHON_BUILD" \
  --archive "$PYTHON_ARCHIVE" --sdk "$KIT/sdk" --profile "$KIT/profile.json" --output "$CPYTHON"
```

## 新配方独立复验

以 `db563402` 的脚本分别在两个全新断网容器运行上面的构建和打包命令。构建
命令使用 `--source-date-epoch 1795759570 --make-jobs 1`，两次均使用同一只读
工具、源码和 SDK，分别提取源文件并从空构建目录开始。显式时间覆盖容器环境给的
`SOURCE_DATE_EPOCH=0`。两份新 XPK 的 SHA-256 都是
`24791dcffe72bb428c8b8886be4d1325114f2c571014f52139e204629019740b`。
两份 CLI 回执和两份 372 行原始 make 日志也分别逐字节相同。运行时 ELF 仍与
冻结发行一致，新的 XPK 摘要对应这一配方。该 XPK 的客体验收沿用发行专项流程。

首次回执收集误将 patch 输出并入 JSON 解析。实际构建和打包已完成，核对正式打包器
的完整性回读结果和原始日志后恢复首份回执。第二次同时独立重算了实际 XPK 的摘要。
[两个独立接收回执](../reports/glibc_v2_cpython_receiver_20261127/serial_replays.json)
