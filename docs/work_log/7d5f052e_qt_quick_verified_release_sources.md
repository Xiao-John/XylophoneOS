# 7d5f052e · Qt Quick 原始发行源码与重编译验收

2026-11-27 · 基线 `093c82c7` · Qt 6.8.3 · Linux arm64 宿主、x86-64 XOS glibc 目标。
沿用 [#303 记录](53ac8baf_qt_quick_release_materials.md) 中的套件、应用对象和原始归档成员账本。
本轮下载官方 Qt Declarative 原档，完成源与许可声明核对，从该归档重编两个静态库并重链接
已知外部 QML 应用。原始回执及其范围保留。

## Qt Declarative 原档及复编

Qt 官方归档大小为 36,503,988 字节，发布者摘要、仓库源锁与实际文件摘要均为
`1f03a2b8f5588b4face7da87926e9b2c1372b3a32157c52df07a75067a9db1af`。应用两份 XOS
QV4 补丁和 allocator 后，全部 53,154 个普通文件与既有构建观察源树逐字节一致。相对原档
修改 7 个文件、新增 1 个文件，源树对照回执列出各路径。
[官方归档摘要](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtdeclarative-everywhere-src-6.8.3.tar.xz.sha256)

```sh
python3 -B src/ports/qt6/quick/rebuild_declarative.py --kit "$KIT" \
  --source-archive "$DECLARATIVE_RELEASE" --output "$REBUILD" --jobs 1
python3 -B "$MATERIALS/relink.py" relink --materials "$MATERIALS" \
  --expected-manifest-sha256 "$MATERIALS_SHA256" --output "$APP_RELINK" \
  --replace "link/kit/target/lib/libQt6Qml.a=$REBUILD/build/lib/libQt6Qml.a" \
  --replace "link/kit/target/lib/libQt6Quick.a=$REBUILD/build/lib/libQt6Quick.a"
```

在断网 Linux 容器中使用 CMake 4.4.5、GCC 16.2.0 与 binutils 2.47。macOS 共享目录上的
`syncqt` 文件移动失败，改用 Linux 文件系统。三任务编译因内存压力停止。串行重建时 Quick
生成的类型注册编译单元仍触发内存终止，尝试限制该进程地址空间后也明确失败。将本轮已生成的
两份预编译头按原摘要和时间保存到外部构建卷，并保留原路径映射，再以原编译参数继续同一 Ninja
树，剩余步骤完成。回执保留各段原日志摘要。

新 QtQml 与 QtQuick 归档分别为 `32026716…`、`21f52978…`，两者与旧套件归档均有字节
差异。使用接收者静态重链接入口同时替换两份归档，形成新的 ELF `bedd3609…`。从迁移后的
材料目录原样重链接仍逐字节复原原始 ELF。链接警告与完整产物摘要见回执。

## 归档成员、宿主与 SDK

对 18 份归档按原 Ninja 链接顺序核对 1,066 个成员。其中 QtBase 10 库 598 个成员、Qt
Declarative 8 库 468 个成员，后者仍留存的全部对象均逐字节匹配。1,024 个直接编译源
中 848 个有文件 SPDX 声明，其余直接源均有范围匹配的 Qt 组件归属。其余 42 个是构建生成
输入，记录 MOC、资源、类型注册、插件及生成的解析器来源。FreeType、HarfBuzz、PCRE2、
zlib 和 MASM 保留各自上游归属和许可文本。包含的头、生成输入、嵌入资源和多许可证分支的
最终许可结论仍须按成品核对。

宿主两套前缀内的 23 个 Linux arm64 ELF、17 个静态归档及 8 个启动或 CMake 文件，全部
逐字节对应原 QtBase、Qt Declarative 或 Qt Shader Tools 构建产物。回执列出工具的直接编译
来源及 `DT_NEEDED`。宿主动态依赖来自 Linux 运行环境。宿主静态归档的逐成员与第三方传递许可
仍待审查。

独立 SDK 源码包复用 Qt 所绑定的 glibc 2.44、GCC 16.2.0 归档和原签名材料。迁移后复验
495 个条目，原锁定签名已用 `gpgv` 重验。旧 SDK 的 256 个 XOS 构建输入全部与 `bac10c6d`
匹配。另一 preview 的 SDK manifest 与 profile 不同。此轮保留 compiler seed 原始摘要，完整
GNU 工具链 seed 和独立 C++ SDK 复编未运行。

## 客体与画面探针

在 Qt 源码提交 `7d5f052e` 普通镜像首次运行到窗口提交后，旧探针截到仅行 40–90 完成复制
的部分画面。旧逻辑见到左上背景即检查文字，获得 0 个文字亮像素而失败。本轮保留该 QMP 原始
截屏和串口。修订后探针在同一时间窗内等待背景和文字都出现。用真实部分画面和完整画面按顺序
回放，确认第一次不提前退出，第二次取得 475 个亮像素。

使用含探针修订的源码 `7e59ec71` 重建普通镜像 `b279c8664a5cef66`，在 QEMU 11.1.2 的
xsh 用同一新 ELF 验证。实际画面 800×600、475 个文字亮像素，画面 SHA-256 与 #303 参考一致。
输入线程已回收，应用退出 0。应用和图形服务结束后分别回到 `121620 / 5 / 3` 和
`129696 / 3 / 1`。ABI 文档检查通过。主线组合的两种入口复验见下节。

```sh
python3 -B tests/qt6_quick_kit_guest.py --system "$SYSTEM" \
  --receipt "$APP_RELINK/receipt.json" --kit-manifest "$MATERIALS/link/kit_manifest.json" \
  --output "$GUEST_PROOF"
```

Qt 原始发行材料包和对应 SDK 源码包均保留在本地，实际发行渠道、安装信息及上述许可范围仍待
核对。[重编、重链接与客体证据](../reports/qt_quick_release_source_20261127/manifest.json)

## 与最新主线的两种入口

基于 `393a60bb` 组合重建普通镜像 `470422325ebe087f` 和匹配的 dash。原档重新编译
的 QtQml 与 QtQuick 双替换 ELF 分别经 xsh 和 dash 启动。两个实测画面均为
800×600、475 个文字亮像素，完整画面 SHA-256 相同。应用和图形服务退出后均回到
各自资源基线，ABI 对照通过。
[主线组合的两种入口回执](../reports/qt_quick_release_source_20261127/manifest.json)
