# d25c5def · glibc 独立源码重建与 loader 材料修复

从 #304 样例归档的源码目录运行正式完整构建。首次实际构建了替换版 `libc.a`，后续终端支持编译因缺少 `src/user/loader/image_reader.hpp` 中止。终端材料一直登记两份 loader 实现文件，遗漏其局部头目录。现在将 loader 局部 `.hpp` 纳入同一个输入哈希与随包源码路径。

原版与替换版的 `load.cpp` 均核对为当初构建时的 Git 对象。用相应源码提交补齐四份局部头，在原材料字节副本上使用修正后的终端构建器，形成 312 和 320 项输入。原样例与首次失败证据保留。

## 完整构建和替换客体

Linux arm64 断网容器只挂载修正源归档及隔离的区分大小写宿主卷。两个变体都从签名 GNU 源经过配置、实际编译、安装和终端支持构建，输出 `static_sdk_built`。两份 SDK 都实际导出四个 loader 头，每个字节摘要与其输入绑定一致。

分别比较重建和原样例的两份 libc。每个变体的归档均为 1,683 个成员，顺序与可见全局符号定义集合逐项一致。两份原始归档与各自重建产物摘要不同，移除调试节后仍有字节差异。逐对象比较两组各 1,683 个 ELF 成员，所有可分配节的属性、尺寸和值逐项一致，包括可执行节。

从两个重建 SDK 生成各自的 C profile，以重建原版 SDK 编译一次同一探针。重链接只替换成重建的另一份 libc。QEMU 11.1.3 在镜像 `17cebdf4873d898e` 中运行两份 ELF，原版得到 ENOSYS；替换版得到成功、EINVAL 和 ENOENT。分别退出 0 并回到 `129793 / 2 / 0`，FAT 读回程序和测试文件字节一致。
[完整构建、故障及客体回执](../reports/glibc_detached_source_rebuild_20261127/report.json)

## 修正后的材料样例

本地修订归档 `glibc-static-relink-materials-corrected-20261127.tar` 保留历史样例的链接工件，补齐两个对应源码根与终端材料中的局部头。在另一无网络容器仅挂载归档和输出目录，逐一核对 1,451 项，并重链接出与 #304 客体运行字节相同的两份 ELF。修正源码归档和原 #304 样例均独立保留，回执记录各自产物摘要与范围。

完整样例解包后从 `static-relink-materials/README.md` 进入；两个源码根位于 `source/original/xos-inputs/` 和 `source/replacement/xos-inputs/`。仅重建 C SDK 时使用修正源码归档，在空目录解包，并把 `OUTPUT_ROOT` 设为构建卷中的绝对路径。

```sh
tar -xf "$CORRECTED_SOURCE"
mkdir -p "$OUTPUT_ROOT"
for variant in replacement original; do
  (cd "corrected-source/$variant" &&
    python3 scripts/build_glibc_sdk.py --archive ../glibc-2.44.tar.xz \
      --output "$OUTPUT_ROOT/$variant" --jobs 2)
done
```

此次是静态 C SDK 完整重建与替换样例。选定 C++ SDK 的重新装配、正式发版工件、逐库成员材料及默认 SDK 切换仍依照对应门验收。
