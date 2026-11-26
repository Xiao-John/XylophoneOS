# XOS Qt Quick 6.8.3 对应源码和静态重链接材料

这份材料对应 Linux arm64 Qt Quick 套件和其中已验证的 x86-64 XOS glibc 外部示例。
材料清单固定套件清单、三个 Qt 组件的源码形态，以及所有随附文件的字节数和 SHA-256。
发行者可在发布通道同时公布材料清单的 SHA-256，接收者可用它校验证据根。

## 校验与重链接

```sh
python3 -B relink.py verify --materials . --expected-manifest-sha256 "$MATERIALS_SHA256"
python3 -B relink.py relink --materials . --expected-manifest-sha256 "$MATERIALS_SHA256" \
  --output "$OUTPUT"
```

重链接需要与应用回执字节一致的目标 `x86_64-elf-g++`、`as` 和 `ld`。工具从 `PATH`
解析，也可通过 `--tool-prefix` 指定其他前缀。材料包含真实外部应用的对象文件、生成的
QML 与资源对象、Interactium QPA 静态库，以及顺序固定的链接输入和所需 SDK 对象。
链接输出必须是静态 x86-64 XOS 可执行文件，原样重链接须还原原始 ELF 的 SHA-256。
重链接过程只执行编译器驱动的链接步骤，原应用目录和生成器均可离线保留在包外。

从随附源码重建 Qt 后，可以替换指定目标归档。使用同一 SDK 和 ABI 重建要替换的库。
同一归档在链接序列中出现多次时，替换在每次引用生效。替换的文件摘要及新 ELF 摘要
保存到输出回执。若修改要求更新对应的 Qt 资源初始化对象、插件或其他归档，也应按原
构建配方重新生成这些输入。

```sh
python3 -B relink.py relink --materials . --output "$MODIFIED_OUTPUT" \
  --replace "link/kit/target/lib/libQt6Quick.a=$REBUILT_QUICK"
```

## 对应源码与构建配方

- `sources/` 中的 QtBase 和 Qt Shader Tools 是对应版本的原始锁定归档。`notices/`
  保存原套件的许可文本和所有三个源锁。材料清单标明 Qt Declarative 的源码形态。
- `locked_upstream_archive` 对应直接校验原始 Qt Declarative 归档。`observed_patched_source_tree`
  保存实际用于构建目标 Qt Declarative 的完整已修改源树。它与可搬移套件中的 QtQml、
  QtQuick 目标归档同时绑定。官方原始归档的 SHA-256 已与仓库源锁交叉核对。对它应用
  仓库里的两份补丁并加入 allocator 后，新树的 53,154 个普通文件与该观察源树逐字节
  相同。两份归档的摘要各自记录在材料清单与原始源码对照中。
- `recipes/xos/` 包含 XOS Qt 补丁、编译辅助工具、QPA 源码、接口头和已记录的构建配方。
  `recipes/build_record.json` 保存观察到的 Release、静态构建和 Qt 功能开关。相对路径
  以该目录中复刻的 XOS 布局为准，宿主和目标输出目录可以重新选择。
- `target_members.json` 是原套件所含目标 Qt `.a` 的归档顺序、成员名和成员摘要账本。
  宿主工具、SDK 运行库和 Qt 此前 Widgets 构建的逐成员账本各有自己的范围。实际纳入
  新示例的库和对象由 `link/plan.json` 固定。

按随附 `recipes/xos/docs/work_log/` 的构建顺序生成 Qt。先从锁定的 QtBase 构建
同版 Linux arm64 生成器。依 Qt Shader Tools 配方应用 `host_qsb_plugins.patch`，构建并
安装原生 `qsb`。再从同版 QtBase 用现有 glibc 工具链构建目标 QtCore、QtGui 和随带
依赖。目标配置按配方应用 `glibc_qtcore.patch` 和 `glibc_qtbase_platform.patch`，采用
XOS Interactium QPA。最后使用同版 Qt Declarative 宿主工具和目标 QtBase 配置构建
静态 Qt Declarative。原始源码形态需应用两个 QV4 补丁和当前端口的 allocator 源文件，
观察源码形态已包含这些改动。原有 Qt Quick 外部样例工作记录列出了目标模块安装和
CMake 插件索引的步骤。`recipes/application/` 保存可由接收者修改的外部示例源码。

## 从原始 Qt Declarative 归档复编

在 Linux arm64 上准备既有可搬移开发套件和其中 C/C++ SDK 绑定的目标工具。运行入口从
源锁核对上游归档，应用 XOS QV4 补丁和 allocator，再用开发套件已有的 QtBase、宿主
生成器及 SDK 静态构建 QtQml 和 QtQuick。CMake 及 Ninja 在 `PATH` 中可用。源码与构建
目录须采用 Linux 文件系统。Docker Desktop 传入 macOS 文件共享目录时，`syncqt` 的头文件
移动失败。低内存环境可以限制并行数。

```sh
python3 -B src/ports/qt6/quick/rebuild_declarative.py --kit "$KIT" \
  --source-archive "$DECLARATIVE_RELEASE" --output "$REBUILD" --jobs 1
```

输出包括 `build/lib/libQt6Qml.a`、`build/lib/libQt6Quick.a`、编译记录和回执。按
`relink.py --replace` 将重编译的归档用于示例应用。生成绑定时同时核对套件、SDK、工具与
补丁摘要。QtBase 及宿主工具的独立复编路径仍按前述配方执行。
[Qt 官方原始归档摘要](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtdeclarative-everywhere-src-6.8.3.tar.xz.sha256)

## 独立 glibc C/C++ SDK 材料

在 XOS Git 工作树从专门入口整理开发套件所用 SDK 的对应源。配方复用已有签名验证报告、
glibc 2.44 和 GCC 16.2.0 官方归档，另从 `bac10c6d` 恢复并核对旧 SDK 的 256 个 XOS
构建输入。SDK manifest 和 profile 需要与此套件一致。其他候选的原始上游归档在摘要相同时
可复用。两个 SDK 的 manifest 或 profile 不同代表不同二进制构建。

```sh
python3 -B src/ports/qt6/quick/stage_sdk_sources.py --kit "$KIT" \
  --glibc-source "$GLIBC_RELEASE" --gcc-source "$GCC_RELEASE" \
  --sdk-revision bac10c6d08bbc454e4068360e04e3058efd14855 --output "$SDK_SOURCES"
```

## 发行范围

此材料覆盖 Qt 源码、修改、来源与声明记录，以及本外部应用的静态重链接。目标静态库的
直接编译文本与 Qt 组件归属已登记。生成资源与生成代码的传递许可、宿主静态归档内部组成、
SDK 继承的工具链 seed 重建、最终产品的安装信息和发布方式仍按发行组成核对。
`notices/runtime/` 标识此次链接采用的 SDK 清单与 profile。各应用分发需要自己的应用对象
或源码及重链接材料。
[Qt 6.8 许可说明](https://doc.qt.io/qt-6.8/licensing.html) ·
[GNU LGPLv3 §4](https://www.gnu.org/licenses/lgpl-3.0.html)
