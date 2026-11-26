# b7e8b6d7 · Qt Quick 生成成员与宿主静态归档来源

2026-11-27 · 基线 `af47b2c5` · Qt 6.8.3。沿用
[源包、目标成员及宿主文件回执](../reports/qt_quick_release_source_20261127/manifest.json)。
逐项审查 42 个目标生成成员及 Linux arm64 宿主套件的全部 17 个静态归档。输出的
`xos_qt_quick_release_provenance_v1` 可以按原归档、成员、资源路径和实际输入重新查验。

## 目标生成成员

42 个成员来自 14 份目标归档。留存的 34 个对象和生成文本通过摘要核对。早期 QtBase
构建树缺失 6 个 AUTOMOC 和 2 个 rcc 生成文本。用保留的 CMake、Ninja 记录、Qt 生成器
和套件绑定的目标 GCC 在独立目录复演。8 个生成对象均逐字节等于原归档成员。Core 的
AUTOMOC 扫描还需要未留存的 MIME 数据生成源码，按原 CMake 命令和原始 Tika XML 重建后
复演通过。清单保留原生成文本缺失和新生成物相符的各自证据。

记录包括 AUTOMOC 的实际头文件与生成 include、QML 类型注册的元类型和参数文件、qlalr
语法输入以及 CMake 插件和 `qmldir` 模板。资源记录直接从静态成员的 ELF 符号与 Qt
资源树解出，核对每个路径和 payload 的摘要与长度。18 个目标 rcc 对象中的 311 次资源
出现均与原 `qrc` 输入一致，包含由 qsb 生成的 150 次输出。着色器输入和依赖文件保留
逐项摘要。资源实际字节与来源声明均有记录。
[Qt 资源系统](https://doc.qt.io/qt-6.8/resources.html) ·
[Qt Shader Tools qsb](https://doc.qt.io/qt-6.8/qtshadertools-qsb.html)

## 宿主静态归档

套件中的 17 份宿主静态归档共含 823 个成员，全部与原 Ninja 顺序和留存对象相符。667 个
直接编译输入都有文件 SPDX、REUSE 或上游组件归属。156 个生成输入包括 144 个 JPEG
编译变体拷贝、10 个 AUTOMOC 和 2 个 rcc。JPEG 的每个副本与原始源文件字节一致，并核对
12 位或 16 位变体的编译定义。静态宿主归档包含的 3 次资源出现均以实际 ELF 对象核对；
其中包括宿主 QtGui 的 ICC 配置文件和两份预编译着色器。

## 清单及验证

```sh
python3 -B src/ports/qt6/quick/audit_release_provenance.py \
  --target-inventory "$TARGET_MEMBER_SOURCES" --target-inventory-sha256 "$TARGET_RECEIPT_SHA256" \
  --host-inventory "$HOST_FILES" --host-inventory-sha256 "$HOST_RECEIPT_SHA256" \
  --qtbase-source "$QTBASE_SOURCE" --qtbase-target "$QTBASE_TARGET_BUILD" \
  --qtbase-host "$QTBASE_HOST_BUILD" --qtbase-target-prefix "$QTBASE_TARGET_PREFIX" \
  --qtdeclarative-source "$DECLARATIVE_SOURCE" --qtdeclarative-target "$DECLARATIVE_TARGET_BUILD" \
  --qtdeclarative-host "$DECLARATIVE_HOST_PREFIX" \
  --qtshadertools-source "$SHADERTOOLS_SOURCE" --qtshadertools-host "$SHADERTOOLS_HOST_BUILD" \
  --target-compiler-sha256 "$GCC_SHA256" --replay-output "$REPLAY_DIR" --output "$PROVENANCE"
```

在原生成器可以运行的隔离 Linux arm64 环境中执行，复演输出位于新目录。证据从已搬移的
Qt Quick 套件独立读回 42 个目标成员、823 个宿主成员和 314 次资源出现，核对本地已匹配
的 5 个套件生成器。故意更改成员摘要、遗漏目标生成成员或改动嵌入资源摘要时，
`verify_release_provenance.py` 均拒绝。`kit_readback.json` 保存验证结果，根清单
固定 gzip 字节。成员的 `generation.source.present` 和 `generation.replay.status` 标识原
文件留存与复演结果。`declaration_evidence` 记录输入或生成链的来源声明。QML、静态库和
资源证据均可从 [报告根清单](../reports/qt_quick_release_member_provenance_20261127/manifest.json) 读取。

QtBase 发行源码内两份预编译 GLSL 着色器在目标和宿主各出现一次。嵌入内容和相邻 GLSL
源码已绑定，上游产生这两份 `.qsb` 的原始工具和参数缺记录。成品实际采用的许可分支、
依赖头和构建工具传递许可，以及安装信息和发行方式需按最终发行组成核对。
