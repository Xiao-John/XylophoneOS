# eb674281 · ClarkE JSC 静态线程边界

2026-11-26 · 从 `0aaca559` 开始。按源锁核对 WPE WebKit 2.54.2 归档（49,565,492 字节，SHA-256 `f3284e19e47fcb5ac8c63c2e1c113dbd65b2423eb8a545f5b345707829004f56`），只读取相关 CMake、WTF 线程与 JSC 根采集成员。对照 `jsc-system-malloc-build.log`（SHA-256 `6e03ac7d9a1a580805469b05a26cc2b28526f095752ce278ad02277b02aceda5`）核实最先报错的类型选择和宿主 ranlib 警告。后续接入要求见 [静态 JSCOnly 线程契约](../contracts/clarke_jsc_threading.md)。

实现独立的 `query_stack_bounds`。真实 glibc pthread 查询当前及存活线程，检查范围并保留错误和输出契约。探针验证主线程和工作线程实际栈位置，工作线程自身和外部查询结果相同，指定栈大小，过期句柄拒绝，互斥与条件唤醒，实时时钟的到期行为，两轮 TSD 析构及 join。WTF 的跨线程根扫描、协作安全点和目标 JSC 静态链接未执行。

Linux arm64 镜像 `xos-campaign-proof:g2-native-retry`（映像 ID `sha256:f2b2390ee0efa349d4d6c37eeb41694d7f002f0301ed09b9998da3d8bbc3b450`），GCC/G++ 16.2.0 与 GNU binutils 2.47 的六个工具文件均匹配 SDK manifest。QEMU 11.1.3、单 CPU、512 MiB、无网卡，临时 FAT 盘在有界 tmpfs。通过已验的 `xos-compiler` wrapper 和 SDK C++ 头列表编译 `-std=c++23 -O2 -Wall -Wextra -Werror`。ELF 有三个 LOAD 和一个 TLS 段，静态入口无解释器。候选 libc 链接器仍报告 `raise`、`__getcwd` 缺口。`xsh` 输出 `CLARKE_THREADING_OK`，退出 0，资源前后为 `129714 / 3 / 1`。

复跑时用已绑定 `${XOS_ICU_SDK}`、`${XOS_ICU_CXX_INCLUDES}` 和 `${XOS_ICU_CXX}` 的目标 wrapper。用已有 [SDK 配置与 wrapper](../../src/ports/webkit/icu/README.md)，无需构建 ICU。C++ 包含路径取 glibc `create_xypm_profile.py create --cxx` 生成配置的 `sdk_binding.cxx_runtime.include_directories`。`${XOS_CXX_WRAPPER}` 的名称是 `cxx`。

```sh
"${XOS_CXX_WRAPPER}" -std=c++23 -O2 -Wall -Wextra -Werror \
  -Isrc/ports/webkit/threading src/ports/webkit/threading/xos_stack_bounds.cpp \
  tests/fixtures/webkit/threading_smoke.cpp -o build/clarke-threading-smoke.elf
x86_64-elf-readelf -l build/clarke-threading-smoke.elf
python3 tests/qt6_sdk_probe.py --image "${XOS_PROBE_ISO}" \
  --payload build/clarke-threading-smoke.elf --marker CLARKE_THREADING_OK \
  --report build/clarke-threading-guest.json
```

| 工件 | SHA-256 |
| --- | --- |
| glibc C/C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| glibc C/C++ SDK 树 | `2070dbad9ddd860a11dd1511f1268c1f62683df01d1a967bfa741e53df0799d6` |
| `xos-x86_64-glibc-clarke-threading-cxx` profile | `8412dc289dfd23a783229833a929b131e458a5427f28608e4106f3c16cf7271d` |
| 系统 `8d7525f679d42e69` manifest | `7b368f7eed0c02d412b60241202a4501eb244f8c5262030930eb62c4a3ba48f0` |
| 系统 ISO | `0c5393c3224acadeffee5cebe239fcc066fac9bb5863debfeaf6b9d9a4dbae26` |
| 栈适配器 `.cpp` | `af13b958043e3b1fccec59a1b9e4796c6127d3d806d1f64dd1c1fe19eb122b03` |
| 栈适配器 `.hpp` | `265d42ea59bed1c1a947d40e2568fee3fd1b544ea82b2ad1bf0690115f7581b6` |
| pthread 探针 `.cpp` | `c95cb597e45e523b46284b75a0fcb2ac5b27d8da4ffc7ce379d891cfd10f933b` |
| `build/jsc-threading-results/clarke-threading-smoke.elf` | `c646cc229ad6872fd30cd1fc897fbdbe2ca3f3cbb83c7192922b7d4faa546a68` |
| `build/jsc-threading-results/clarke-threading-guest.json` | `38fbfd52249356da5bb5391316fc22f5178a919d7a2efd44c9fe84a655f455a8` |
| `build/jsc-threading-results/clarke-threading-guest.serial.log` | `e228f98f429bd98e31fc216b63ed663868b9354240911088f9771154a7ab1a5a` |
