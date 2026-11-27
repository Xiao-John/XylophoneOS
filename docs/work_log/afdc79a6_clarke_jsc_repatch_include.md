# ClarkE WebCore 的无 JIT 编译

2026-11-27。基线 `08b0bd46`，修复 `afdc79a6`。在 WPE WebKit 2.54.2
目标配置下，`ENABLE_JIT=0`、`ENABLE_C_LOOP=0`、`WEBKIT_MAX_BUNDLE_SIZE=2`，
`UnifiedSource-bytecode-44.cpp` 暴露了 `Repatch.cpp` 对相邻编译单元的隐含
头文件依赖。目标 GCC 在解析该文件时只看到 `CallLinkInfo` 的前置声明。

原生 LLInt 的默认、虚调用和多态调用慢路径仍调用这一组代码。本补丁直接包含
`CallLinkInfo.h`，并将补丁登记到软件 WebCore 源锁。保留了 LLInt 的调用缓存、
WebAssembly 功能选择和已有 JIT 编译条件。无需改变 XOS 公共 ABI。

## 复现

使用[软件 WebCore 配置](../../src/ports/webkit/page/README.md)与配对的静态
glibc C/C++ SDK。指定 `WEBKIT_MAX_BUNDLE_SIZE=2`，使用原生 x86-64 LLInt
并关闭 JIT 与 WebAssembly。将上游包交给锁定源准备器，使用 GNU patch，
然后配置 Ninja 构建目录并构建失败单元。

```sh
python3 -B src/ports/webkit/page/prepare_source.py \
  --archive "$WPE_ARCHIVE" --output "$PREPARED" --patch "$GNU_PATCH"
ninja -C "$WEBKIT_BUILD" \
  Source/JavaScriptCore/CMakeFiles/JavaScriptCore.dir/__/__/JavaScriptCore/DerivedSources/unified-sources/UnifiedSource-bytecode-44.cpp.obj
```

从锁定归档全新解包并应用全部补丁。与上一次构建的源树逐文件比对，除修复的
`Repatch.cpp` 外另有 39,115 个常规文件均字节一致，原目录有两个构建期间生成的
Python 字节码缓存。新准备回执 SHA-256 为
`47cc2b6ca48364ddbb00a6a9bc79aec31e9e6556f8afefa03d2ebf81530b8810`。

修复单元以实际全量目标编译命令和目标 GCC 16.2.0 产生 x86-64 ELF relocatable。目标 `nm`
核对 `linkMonomorphicCall`、`linkPolymorphicCall` 和 `jsToWasmICCodePtr`
均有定义。对象 SHA-256 为
`e879ce0f7291764ba81f2f1a7a5cf27317668100751be5f8c431dba846f9411c`。
独立对象验证和全量目标续跑产生相同的对象摘要。定位错误后，在旧构建处理到
第 912 项时主动中断并保留日志，新构建复用其余可用对象。此回执覆盖该编译单元，完整归档、
链接闭包与客体资格仍待验证。
