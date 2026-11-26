# 53ac8baf · Qt Quick 对应源码与静态重链接材料

2026-11-26 · Qt 6.8.3 · Linux arm64 宿主 · x86-64 XOS glibc 目标。
在主线 `3dbc304e` 上补齐可搬移套件的对应源码副本、下游构建配方、静态重链接入口和
目标归档成员账本。应用使用[原套件](870aabad_qt_quick_relocatable_kit.md)的同一份
外部 QML 示例对象。材料清单绑定 361 个文件，目标账本绑定 18 份归档及按归档顺序
记录的 1,066 个成员。

## 来源与复建

QtBase 和 Qt Shader Tools 是与仓库源锁摘要一致的原始压缩归档。Qt Declarative
来自原构建器 `CMAKE_HOME_DIRECTORY` 指向的实际已修改源树，共 56,738 个归档项。
导出时比对了 QtQml 和 QtQuick 目标归档与已安装套件的摘要，并验证 QV4 allocator
源文件与 XOS 端口一致。已修改源树与上游原始压缩包是两种独立的输入形态，清单分别
记录它们的摘要。构建配方携带 XOS 修改、宿主和目标构建记录，以及可修改的示例源码。

```sh
python3 -B src/ports/qt6/quick/release_materials.py --kit "$KIT" \
  --qtdeclarative "$DECLARATIVE_SNAPSHOT" --declarative-built-snapshot \
  --qtshadertools "$SHADERTOOLS" --build-record "$QT_BUILD_RECORD" \
  --application-build "$APP_BUILD" --application-source "$APP_SOURCE" --output "$MATERIALS"
tar -C "$MATERIALS" -cf - . | zstd -o "$MATERIALS_ARCHIVE"
tar --zstd -xf "$MATERIALS_ARCHIVE" -C "$MOVED_MATERIALS"
python3 -B "$MOVED_MATERIALS/relink.py" relink --materials "$MOVED_MATERIALS" \
  --expected-manifest-sha256 "$MATERIALS_SHA256" --output "$RELINK_OUTPUT"
```

`MOVED_MATERIALS` 为预建的空目录。断网 Linux arm64 容器挂载迁移后的只读材料，
原 Qt 安装前缀、原应用与生成器目录留在容器外。使用原回执绑定的 GCC 16.2.0 与
binutils 2.47，原样重链接还原 ELF `fefc6355…`。第二次用目标 `objcopy` 给
`qquickitem.cpp.o` 加入未装载的 `.xos_relink_proof`，用 `ar rD` 更新 QtQuick
归档副本，再通过 `--replace` 重链接。`readelf -SW` 和 `readelf -p` 在新 ELF
`6a1d6bf1…` 上读出该节及原样文本。重链接器对内容变更、额外文件及特殊文件均拒绝
校验。两次链接出现相同的现有 glibc 未实现接口警告，回执保留警告清单和原始输出摘要。

## 客体验证

冻结源码 `53ac8baf` 用 `scripts/build.py --output-dir "$SYSTEM"` 重建普通镜像
`f129209799d58b4b`，ABI 文档对照通过。`LWIP_ARCHIVE` 沿用主线已锁定的 lwIP 2.2.1
源包，构建时传入 `XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE"`。用 QEMU 11.1.2 和
现有外部应用夹具从 xsh 启动修改归档所得 ELF。程序显示 800×600 画面、475 个文字
亮像素，输入线程正常回收，应用退出 0。应用退出后当前图形服务资源恢复至
`121620 / 5 / 3`，图形服务退出后恢复至原基线 `129696 / 3 / 1`。

```sh
python3 -B tests/abi_doc_consistency.py
python3 -B tests/qt6_quick_kit_guest.py --system "$SYSTEM" \
  --receipt "$MODIFIED_RELINK_OUTPUT/receipt.json" \
  --kit-manifest "$MOVED_MATERIALS/link/kit_manifest.json" --output "$GUEST_PROOF"
```

## 产物和验收边界

本地归档 `build/release-materials/xos_qt_quick_release_materials_final.tar.zst`
为 125,086,915 字节，SHA-256 为 `0c585b26e8fc93d863083a447f49a6a4617fa6a289ca3e55bb35eea98c0db654`。
解包后的 `manifest.json` 摘要为 `28566ca68b6d902dafa62bb90f60de1fa30631dd189977c3777ad361446ae676`。
逐成员 SPDX 表达式、宿主工具许可与对应源、独立 glibc C/C++ SDK 的源码分发范围以及
实际发行渠道和安装信息仍待核对。完整 Qt 重新编译和替换 ELF 的 dash 入口未运行。
本次生成的归档保留在本地。
[构建、重链接与客体回执](../reports/qt_quick_release_materials_20261126/manifest.json)

## 主线组合入口复验

以 `863946ac` 合入本 PR 的 `6196b02e` 得到 `a1bdc89d`，重建普通镜像
`20f8c42fae412943` 和同镜像的 dash。替换 Qt Quick 归档成员所得 ELF 分别从 xsh 和
dash 通过。两个客体都显示 800×600、475 个文字亮像素，画面摘要相同。应用和图形服务
两个退出点恢复各自的资源基线，ABI 表对照通过。
[组合绑定及两种入口回执](../reports/qt_quick_release_materials_20261126/manifest.json)
