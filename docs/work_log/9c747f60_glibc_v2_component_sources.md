# 9c747f60 · glibc v2 发行组件对应材料

以已验收 v2 发行清单的 SHA-256
`b2b417bdf2fed26d02d22786cf1ed39fa5036324a6b6514bab3e89fdfefd82ef`
为输入，收集系统安装器中的 Dash、每日工具、CPython/zlib 和 IDNA 的对应材料。
材料取自候选源 `8e66789c` 和 CPython 构建源 `417923a4`，使用实际安装介质与
XPK 内的回执逐项绑定。Dash 的目标摘要来自实际 XOSBND1 容器内的 Dash 成员。
CPython XPK 中的解释器、标准库与 zlib 记录绑定到选中构建，两个原始构建回执
的 SHA-256 与产品内嵌回执一致。

补充归档含 135 个文件，共 26,577,204 字节。带入跟踪的 Dash 上游归档，以及
CPython 3.14.9、zlib 1.3.2、IDNA 3.20 的锁定原件。完整 sbase 上游归档按锁定
`c546c3a` 导出，并按 Git 树重算全部文件内容与模式。XOS 修改、构建输入、
许可证及实际版本回执随补充材料保留。四份既有发行归档通过原发行清单摘要引用，
本次补充独立保存。归档以相同输入生成两次均得到同样字节。

## 接收复验

隔离的断网 Linux 容器仅获得补充归档、固定摘要、只含工具和配置的核验目录及
新输出目录。重新核对全部条目及各组件的源、安装成员、构建及 XPK 回执绑定。
错误材料清单摘要被拒。另取包中的原始 wheel、锁、许可与实际 profile，重建的
IDNA XPK 与发行所附文件逐字节一致。用还原的 sbase/XOS 源和精确 v2 SDK
调用 `build_daily_utilities.py` 与 `stage_glibc_daily_runtime.py`，13 个
运行时 ELF 的大小和摘要与发行 XPK 回执逐项一致。
第一次独立打包试跑缺少对应配置和许可文件，
在脱离生产目录的工具包内补齐后通过。

## 复跑

CPython 与 zlib 回执取实际 CLI build 的 `py0a_report.json` 与 libz build 的
`report.json`。已锁定的 sbase 上游仓库以
`git archive --format=tar.gz --prefix=sbase/ c546c3a5724c81cee9a11d816a38ccdf17472129`
输出。XOS 仓库需含两个实际产品源提交，收集器从 Git 对象读入锁定的配方和源码。

```sh
python3 -B scripts/package_glibc_release_sources.py build \
  --release "$RELEASE" --candidate "$CANDIDATE" \
  --cpython-commit 417923a44848e4a2b9385c80e48d78af77c362d0 \
  --cpython-receipt "$CPYTHON_BUILD_RECEIPT" --zlib-receipt "$ZLIB_BUILD_RECEIPT" \
  --cpython-archive "$CPYTHON_ARCHIVE" --zlib-archive "$ZLIB_ARCHIVE" \
  --idna-wheel "$IDNA_WHEEL" --sbase-archive "$SBASE_ARCHIVE" --output "$MATERIALS"
python3 -B scripts/package_glibc_release_sources.py verify \
  --archive "$MATERIALS/component-sources.tar.gz" \
  --manifest "$MATERIALS/component-sources.json" \
  --manifest-sha256 "$MATERIALS_MANIFEST_SHA256"
```

本次补充覆盖实际产品的对应材料、脱离生产目录的核验、IDNA 重打包和每日工具
运行时 ELF 重建。
完整 CPython/zlib 和 Dash 接收方重编、全部静态程序的成员级分发资格及最终发行
组合各走原验收门。未对 CPython 归档另做 Sigstore 签名验收。
[冻结回执](../reports/glibc_v2_component_sources_20261127/manifest.json)
