# c7442fa6 · glibc 静态应用入口与 newlib 回退

源码基线为 `9f7a9a0f791700d15eac60ee03e455948546ce32`。独立应用构建入口
`build_glibc_program.py` 新增 `--profile` 和 `--cxx`。`--profile` 在编译前和发布
ELF 前用现有 xypm 候选验证器重查完整 SDK。`--cxx` 要求候选具备 `cxx_runtime`，
选择该 SDK 的 POSIX libstdc++、libsupc++、libgcc 和 C++ 标头。汇编器与链接器按
清单摘要选择，ELF 先写入独立工作目录并经静态布局检查。`build_glibc_sdk.py` 将
新增构建依赖纳入安装材料与源码清单。正式操作见 [SDK profile 契约](../contracts/xypm_sdk_profiles.md)。

## 既有普通构建证据复核

只读核对 `fresh-final-qualification.json` 的系统镜像、工具、两份 SDK 压缩包和
报告等 11 项所引摘要，全部一致。记录的 Linux arm64 工具环境完成 18 项，普通静态
C 客体 xsh 76 次和 dash 66 次，普通 C++ 各 12 次。原始失败和独立重复报告记录了
同一系统与普通静态 ELF 下的间歇故障。异常探针 ELF SHA-256 为
`eb30c6be89d721816ec8d1c1cc4d8e87c7a4edce211533ecfee6619a2cba8494`。

| 历史普通静态检查 | 失败 | 失败状态 | 报告 SHA-256 |
| --- | ---: | --- | --- |
| xsh 异常单项 | 2/36 | 127，`double free or corruption (out)` | `7d0d0d39dd70f39bbdc24c2a869f273170a528ca8863154b8f08e4c617e71e4f` |
| xsh 顺序运行 | 1/48 | 异常项 127，同一诊断 | `2582b363a108c88a2cb2166d99d9963f4a7786bc558526809cd48b7fe2cbb04e` |
| dash 异常单项 | 1/36 | 127，`double free or corruption (out)` | `9abcd04f6b894659dc3c35d767e41af9ea4dcf95ebf4b9f0267d8221905c3ff4` |
| dash 顺序运行 | 1/48 | 线程项 127，`corrupted size vs. prev_size` | `343f8daaed7d19e83729ce707117b6f3a34ba26a5c08c33350aaa7d5ed4f1d93` |

四个串口原件摘要均与对应报告一致。失败条目的资源计数回到 `[129700, 3, 1]`。
最初 dash 失败报告为 `b22500d45f9b0219d83cd366e51e9405cb51810b36745e74a86fa4a71e1ae9e1`。
历史完整重建汇总为 `b5d0f35e146a583f9307dc9e592b03c2141a83a71c2b198b13f1133a02b66bcf`。
历史诊断链接另有回执。间歇故障的原因尚未确认，默认切换仍受阻。

## 本组构建与客体检查

已认证的 C 与 C++ SDK 来自基线源的 Linux arm64 构建，SDK 清单分别为
`ecfea17a58684c85f7650be99ee62654b5345841ad8f6c04fcf989633c392d4d` 和
`a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e`。
用 GCC/G++ 16.2.0、GNU Binutils 2.47.20260726 与新的构建入口生成三个 ELF。
普通 C 入口与显式候选 C 入口产物完全相同。C++ 建置时使用了指向 newlib 的
`CPATH`、`CPLUS_INCLUDE_PATH` 和 `LIBRARY_PATH`，编译环境清理记录该三项，
编译和链接命令绑定 glibc 头及归档。`tests/xypm_sdk_profile_host.py` 44/44，覆盖
新增的错误运行库 profile 和用 C-only 候选构建 C++ 的两个拒绝项。

使用 `build_glibc_sdk.py --jobs 2` 从锁定 glibc 2.44 源码另行重建 C SDK，
`gpgv` 返回 0。用 `create_xypm_profile.py` 生成新的候选后，从该 SDK 的发行材料
直接运行其中的 `build_glibc_program.py` 成功。新 SDK 清单为
`efc12a09855da3a4e66cde97fff8677cef7e5edd87d9c624884c63f0573fe23e`，C ELF 为
`5b50a90d15c7f16b45b4ee7c1cbfe2035156ad9e8c4c55f5993158d2c8654a95`。该 ELF 在
xsh 和 dash 各运行 3 次正常参数、3 次非法参数，状态分别为 37 和 90，资源全部恢复。
记录位于 `build/runtime_c_rebuild/`，`guest-report.json` 为
`27ec411a4ed9f3c0db2487730a0d63b96bf5e2c46b04866a4357c79a8072f0ed`。

系统 build ID `3c8ccf57d6041f7c`，QEMU 11.1.3，Linux arm64 宿主，x86_64 BIOS 客体。
ISO 为 `dd6e18958a6c543160a3b7823f320d7b8ace72e96c9dcbc50f72a004ea90332e`，
dash ELF 为 `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067`。
使用基线镜像与两个独立工作盘，经 `exec-file` 和 dash 脚本分别运行下列各 3 次。

| 源码或操作 | xsh | dash | ELF SHA-256 |
| --- | --- | --- | --- |
| `glibc_g2/static_main.c` 正常参数与非法参数 | 3 次退出 37，3 次退出 90 | 3 次退出 37，3 次退出 90 | `7d9719a3153d19101df2ee64fafbc7aa87746782cc8af8a249dea49cc3dce2c6` |
| `xypm/glibc_profile_program.cpp` 的线程、TLS、主线程异常捕获 | 3 次退出 0 | 3 次退出 0 | `96404901d0e28e20d2fd268fc9a280cba3152f12536167f922eb001e9fdbcc0d` |
| `cpp_abi/string_vector_probe.cpp` 使用 glibc | 3 次退出 0 | 3 次退出 0 | `adfff7c8346d885d183d49f9bd2597e86e34080f32a882bfa51c8aa9f6a0b8b9` |
| 同一份 `string_vector_probe.cpp` 使用冻结 newlib，执行已安装程序 | 3 次退出 0 | 3 次退出 0 | `cdc15bf5c34cbae1a32ea0744c7cf476b954db7e38675cefbf32b92cac54d10f` |

两个入口合计 30 次资源恢复至 `[129700, 3, 1]`。冻结 newlib SDK 的发行压缩包和
树摘要分别为 `86583de2a13b3eea095e94e3768243fdb40216bdfb7e01bc8909d969331e5f66`
和 `e78726755d11d19feabcb7c36faebf6ed9a4e663f85f6beb081ffabae105a874`。
按冻结 `xos-x86_64-static-single-v1` 使用 `xos_app.py init/build/check/pack`，再用
`xypm.py verify`、`install --offline`、`verify-installed`、`remove --offline`。
测试盘启动前后均核对 28 个包文件，卸载后核对 0 个包文件。卸载后的盘和客体退出
后的盘均可回读原先独立写入的用户文件，内容 SHA-256 均为
`e2637a1628a6e2b3824d7260d7400a48f9da543d1a494caa6d682c222e7f8b1e`。
这是冻结 SDK 与隔离工作盘的回退演练。存量发布系统的整体回退和应用批次的升级、
卸载验收仍待执行。

回执、验证脚本、串口和包数据位于本工作区 `build/runtime_migration_final/`。
`guest-report.json` 为 `3f7e5c3c6dbfa3cad1a24bdca991ca3bde388870f8f82f7d9e5c0a74576c34f3`，
`guest-run.log` 为 `e5a3ad05b4da9e447a2287ac70bc3289a69b091bb785aa79f644bcc51969efda`。
本轮应用检查覆盖顺序运行与受控错误；历史并发异常压力问题继续登记为未解决。
glibc XPK 安装、dash/Qt/xypm 本体迁移、D1–D4、存量批次和默认切换均待独立验收。
