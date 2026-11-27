# 960fce43 · GCC Seed 构建路径

从冻结发行工作盘只读导出 GCC 与 G++ 的两个驱动和两个前端，并逐个核对 GNU
Seed 摘要。四个 ELF 内均有历史宿主目录，按检查顺序分别为 66、67、647 和
674 处，GCC specs 无此路径。GCC 16.2.0 顶层 `configure` 将调用名记入
`TOPLEVEL_CONFIGURE_ARGUMENTS`，驱动的 `-v` 从该记录输出配置；编译源文件
也会经 `__FILE__` 和调试信息保留宿主目录。

构建器从构建目录相对调用上游配置，编译器包装器把项目、SDK、宿主 C++ 头与
库、GCC 源和构建目录映射到稳定的 `/usr/src` 路径。构建器摘要纳入缓存键，
避免使用旧路径策略的缓存。已安装 ELF 若含所选构建路径或常见宿主个人目录，
构建拒绝生成 Seed 回执。默认仍构建 C；`--enable-cxx` 同时要求 g++ 与
cc1plus。

用已锁定的上游配置参数记录片段和宿主实装的 x86_64-elf GCC/G++ 16.2.0 执行
回归。两个含空格的独立构建根生成相同配置文本，两处的 C 和 C++ 目标对象分别
逐字节一致。关闭路径映射得到的四个对照对象均被拒绝。

```sh
python3 -B tests/gcc_seed_build_paths.py --gcc-configure "$EXTRACTED_GCC/configure"
```

## Linux arm64 重建

使用冻结 GNU Seed 源档中的 GCC 16.2.0、GMP 6.3.0、MPFR 4.2.2 与 MPC 1.3.1，
逐档核对 `src/ports/gcc/source_lock.json`。交叉编译时使用冻结 newlib SDK 的
`manifest.json`（SHA-256 `dd95ed9b64cf6b200b6d4ccd6e7539696d0aabc1dabc5a7d8d5b16b39565f59e`）
以及同一 SDK 的 C++ 头文件和 `libstdc++.a`。配置实际识别了 Linux 构建机
`aarch64-unknown-linux-gnu`、XOS 运行宿主 `x86_64-unknown-elf` 和编译目标
`x86_64-elf`。在断网容器中运行了实际的顶层 `configure` 和 `make all-gcc`。

初次 C++ 配置沿用了旧的 C 专用补丁，生成的 make 图缺少 `all-libcody` 规则，
而上游 `cc1plus` 需要链接该库。构建器现在按语言选择补丁集，隔离两种源码缓存，
并把实际补丁摘要记入构建身份。用同一锁定源档重新配置后，生成了
`all-libcody: configure-libcody` 规则，重新进入交叉编译。

下一次构建完成部分依赖后在 `all-build-libcpp` 停止。GNU 顶层 make 把宿主
`CXXFLAGS` 也传给原生生成器，Linux arm64 的 G++ 拒绝其中的 `-mno-red-zone`。
将 XOS ABI 参数留在交叉编译包装器后，新配置完成原生和交叉的两套 `libcpp.a`
以及 `libcody.a`。抽查输入对象的 ELF `e_machine` 分别为 AArch64、x86-64、
x86-64。构建继续生成最终 GCC 工具。

`all-gcc` 随后因缺少构建机的 `fixinc.sh` 停止。上游 GCC 的 `stmp-fixinc`
仍直接使用该脚本。端口补丁保留原生 `all-build-fixincludes` 依赖，只跳过 XOS
宿主侧构件。按修订后的构建图真实生成了 arm64 构建目录中的 `fixinc.sh`。
产物检查按冻结回执和上游安装规则寻找 `x86_64-elf-` 开头的三个驱动；实际 x86-64
静态 ELF 的安装布局检查通过，缺少目标前缀的目录拒绝签发回执。

完整 `all-gcc`、最终 ELF 检查、重新组装发行盘与两种 Shell 客体验收仍待完成。
原发布 GNU Seed 和当前候选的二进制继续保留各自原件。

收口时本次 Linux arm64 容器已退出 1，保留 782 个 GCC 目标目录对象。
`all-gcc` 在 `gcov-tool` 链接遇到冻结 newlib SDK 未提供的 `nftw` 和 `ftw`。
本次尚未运行 `all-target-libgcc`、安装或新编译器的客体验收。

## GCC 重建产物的客体验收入口

用完整 GCC 构建回执和预期摘要核对两个驱动、CPP 与两个前端。验收在已绑定的
glibc 发行初盘副本替换这五个文件，逐项读回并绑定实际启动盘。原安装器、
普通 ISO、Binutils、GNU Make、目标 SDK 和发布工作盘均来自给定的发行候选。
QEMU 客体运行 C/C++、xsh 与 Dash 的 GNU Make、未定义符号拒绝和冷启读回，并从
链接映射核对实际使用的 glibc sysroot。

对照使用 `960fce43` 冻结发行盘实际读取的五个原 ELF，经同一入口重新写入盘副本。
18 项客体检查通过，已登记的软件包和原始发行盘摘要保持一致。错误回执摘要和错误
工具摘要均被拒绝。新编译器仍须使用自己的构建回执运行同一门。
[客体对照回执](../reports/gcc_seed_build_paths_20261127/receiver-control.json)

```sh
python3 -B tests/glibc_gnu_seed_guest.py --release-dir "$RELEASE" --output-dir "$OUTPUT" \
  --rebuilt-gcc-receipt "$GCC_BUILD/manifest.json" \
  --rebuilt-gcc-receipt-sha256 "$GCC_RECEIPT_SHA256"
```
