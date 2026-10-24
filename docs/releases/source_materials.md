# GNU Seed 对应源码材料

本目录随 XOS 0.0.1-1024 发布，提供生成随附 GNU Seed 所需的上游源码原包、仓库记录的 XOS 补丁及配置、实际源码树相对原包的差异覆盖层和可取得的构建记录。完整材料位于 `build/releases/0.0.1-1024/sources/xos-0.0.1-1024-gnu-sources.tar.gz`；包内 `source-materials-manifest.json` 记录每个收录文件的来源路径、SHA-256、大小、各上游原包锁校验及差异路径。

## 收录内容与校验

- GCC 16.2.0、Binutils 2.47、GMP 6.3.0、MPFR 4.2.2、MPC 1.3.1 的原始压缩包；GCC/Binutils 使用仓库 source lock 中的 SHA-256，GMP/MPFR/MPC 使用其中的 SHA-512 校验。
- newlib 原始压缩包及实际 SHA-256。仓库未提供对应上游摘要锁，故该值仅作本次输入的实测标识，不代表上游认证。
- C Seed、G++ Seed、Binutils 实际源码树相对相应原包的新增/修改文件覆盖层，以及删除路径清单。每份 overlay 都对应实际构建用源码目录；清单标示差异数量。覆盖层中的 symlink 标记应按清单语义还原为链接，不能当普通源文件使用。
- GCC/Binutils 移植说明、配置脚本、补丁、兼容头、manifest、上游许可文本、newlib COPYING，以及缓存中可取得的配置/构建日志。另收录本机 Homebrew GCC/Binutils formula 和 `x86_64-elf-gcc -v` 输出作为宿主工具信息。

可用原包解压后，以 manifest 的 `overlays` 路径应用相应差异，并删除 `deleted` 所列路径，从而重建对应的本地源码树。材料并非完整构建环境镜像；没有打包对象文件、可执行构建产物、整个 `.cache` 或 build 树。

## 构建记录与许可边界

包内保留本仓库 `src/ports/gcc`、`src/ports/binutils` 的实际补丁和配置，以及对应 cache 中仍存在的 manifest、config.log、configure.log、build.log 和安装记录。不同阶段或派生 Seed 的文件分别保留其来源路径；记录中的绝对路径仅说明历史宿主构建位置，不能作为客体安装路径。主 Seed 的 GCC target 为 `x86_64-elf`，宿主由记录中的 configure 命令标明。

上游 COPYING、LICENSE、GCC Runtime Library Exception、GMP/MPFR/MPC 与 Binutils/zlib 声明均按实际来源保留。newlib 含多种逐文件许可，不可由项目名推断整包许可证。本次材料收集不构成逐源文件/库归档成员法律审计，也不证明静态库成员到源文件的完整追溯；相关未完成项以仓库 `docs/licensing.md` 和 `licenses/components.json` 为准。

打包器为 Apache-2.0 自研脚本 `scripts/package_release_sources.py`。运行方式：`python3 scripts/package_release_sources.py`。脚本只写此版本目录下的 `sources/`，并在原包与已锁摘要不符时终止。

## 派生重链接源码补遗

发布主源码归档生成后补充发现，两个实际派生 GCC Seed 的 `source/libiberty/lrealpath.c` 未进入原包 overlay：`gxx_lrealpath_v5` 与 `open_capacity_fix`。随附独立补遗 `xos-0.0.1-1024-gnu-source-supplement-gxx-lrealpath.tar.gz`，其中包含两份源文件、派生 seed manifest、父 Seed manifest、重链接脚本和对应 XOS patch。补遗 manifest 绑定主源码归档 SHA-256，并逐项记录补遗输入摘要。原始主归档保持不变。
