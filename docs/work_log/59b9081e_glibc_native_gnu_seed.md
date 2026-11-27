# 59b9081e · 统一 glibc 发行盘 GNU Seed

显式 Seed 装配器以已验收的同 profile daily、CPython/zlib、IDNA 发行目录为输入，生成独立工作盘及安装、普通两份 ISO 副本。使用的系统 build ID 为 `73601d7ff1c68866`，SDK profile 为 `xos-x86_64-glibc-unified-cxx-v1`，glibc 版本为 2.44。装配完成后离线逐文件读回 1,374 项，原发行的三个 XPK 归属和 57 个受管文件继续通过校验。旧盘由原发行归档重新提取，仅作为只读取件来源。
[发行组合实测](9dd3de65_glibc_release_package_composition.md) · [冻结发行回执](../releases/release_0_0_2_1103.json)

| 组件 | 来源与运行库 |
| --- | --- |
| GCC/G++ 16.2.0、Binutils 2.47 | v0.0.2-1103 历史发行逐字节取回的 XOS 原生 ELF，自身保留历史静态运行库。冻结发行清单、原生工具 build manifest、完整 GNU 对应源码与 `lrealpath` 补遗均完成摘要核对。 |
| GNU Make 4.4.1 | 在断网 Linux arm64 构建环境，从锁定源和 GNU 签名重建。签名主指纹为 `6D4EEB02AD834703510B117680CB727A20C79BB2`，构建绑定同一套统一 glibc SDK，入口为 `/usr/bin/gmake`。 |
| 客体新编程序 | GCC/G++ specs 显式选择 `/sysroot` 下经 profile 核验的头文件、CRT、终端与静态运行库。链接使用原生 GNU ld，生成可走 stdio 交接的 x86-64 静态 ELF。客体可从 `/sysroot/xos-profile.json` 读回应用目标身份。 |

## 复现

冻结发布输入取同一个 v0.0.2-1103 资产集合。GNU Make 以被测发行目录中的 `application-sdk` 及实际构建工具重建。源包、签名和 keyring 来自 GNU Make 源锁声明的来源。

```sh
gh release download v0.0.2-1103 --repo Xiao-John/XylophoneOS --dir "$DONOR" \
  --pattern release_manifest.json --pattern '*_images.tar.gz' --pattern '*-sources.tar.gz'
python3 scripts/build_gnu_make.py --archive "$MAKE_ARCHIVE" --signature "$MAKE_SIG" \
  --keyring "$GNU_KEYRING" --sdk "$RELEASE/application-sdk/sdk" \
  --profile "$RELEASE/application-sdk/profile.json" --output-dir "$MAKE_BUILD"
python3 scripts/check_frozen_gnu_seed_sources.py --donor-dir "$DONOR" --output "$SOURCE_REPORT"
python3 scripts/prepare_glibc_gnu_seed.py --release-dir "$RELEASE" --donor-dir "$DONOR" \
  --make-receipt "$MAKE_BUILD/manifest.json" --output-dir "$SEED"
python3 tests/glibc_gnu_seed_guest.py --release-dir "$RELEASE" --seed-dir "$SEED" \
  --output-dir "$GUEST_REPORT"
```

第一份工作盘由装配器建立，第二份由客体验收程序复制。安装器先装入 dash 与 xypm，随后用普通 ISO 冷启并在两种 Shell 执行原生构建。C 夹具调用 glibc 专用的 `gnu_get_libc_version`，C++ 夹具实际运行跨翻译单元异常、析构、RTTI、TLS 和标准容器。Make 配方包含真实 `ar`、`ranlib`、C/C++ 链接与 dash 配方。导出的链接 map 用于验证启动对象及库路径，工作盘再次冷启读回客体构建的 ELF。

本组覆盖显式静态原生开发，工具运行库重建、系统重建、编译器自举及实际最终发布默认分别验收。默认入口由[发行验收表](../releases/glibc_default_gate.md)管理。

## 客体证据

正式工作盘从候选安装 ISO 装入 dash 与 xypm，随后在 macOS 宿主 QEMU 11.1.2 上从普通 ISO 冷启，通过全部 18 项检查。GCC 与 G++ 直接构建并运行两种应用，xsh 与 dash 各执行一次完整 GNU Make 重建。未定义符号被原生 GNU ld 拒绝，无残留 ELF。再次冷启时，两个客体构建的程序均正常退出。所有操作的空闲页、任务和完成记录都回到 `129806/2/0`。安装后和关机后两次验证的受管文件都是 57 项。

C 程序返回 glibc 2.44，C++ 程序完成跨单元异常和 TLS 路径。导出的 C/C++ 链接图核对了统一 SDK 的启动对象、glibc 和 libstdc++，静态归档有由原生 ranlib 写入的符号索引。两次独立装配的工作盘和装配回执逐字节一致。另通过 18 项 Seed 预检和 10 项发行系统许可材料检查。
[实测回执、串口和链接图](../reports/glibc_native_gnu_seed_20261127/manifest.json)

冻结回退使用 v0.0.2-1103 的原安装 ISO 和独立旧盘副本，旧系统 build ID 为 `8356e45af316fc93`。GNU Seed 在原 newlib `/sysroot` 编译、链接并运行 C/C++ 示例，两个顶层操作的空闲页、任务与完成记录均回到 `130207/2/0`。发布镜像归档与测试前的旧盘输入在结束后摘要一致。
[旧系统回退回执](../reports/glibc_native_gnu_seed_20261127/rollback_guest.json)
