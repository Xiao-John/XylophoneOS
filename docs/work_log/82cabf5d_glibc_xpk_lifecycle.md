# 82cabf5d · glibc C/C++ XPK 构建与客体生命周期

2026-11-26 · G4 应用构建入口接受显式 glibc 候选，复用静态 ELF 构建器及 SDK
核验。项目包含多翻译单元和本地头文件时，编译器依赖记录必须落在应用构建输入中。
打包使用同一份经核验的构建回执，逐项核对 ELF 和数据文件摘要，装入匹配运行库的
许可材料。冻结 newlib profile 继续走既有入口。用法见
[候选 profile 契约](../contracts/xypm_sdk_profiles.md)。

Linux arm64 下使用 SDK 清单锁定的 GCC 16.2.0 与 binutils 2.47，QEMU 11.1.3。
将实际构建的 C 应用和调用 libstdc++ 的多翻译单元 C++ 应用打包。宿主在独立 FAT
候选盘完成两次安装、一次 C++ 修订升级、两次卸载。三个独立客体启动分别验证初
装、升级及卸载后的状态。xsh 和 dash 共 9 条命令通过，每条后恢复资源基线。
四项宿主检查确认未登记的头文件被拒绝、改动后要求重建、冻结 newlib profile 拒绝
glibc XPK，以及原盘和用户文件保持原摘要。使用的系统镜像由组合快照
`d87a1453` 构建。回执记录本次应用候选及独立系统 SDK 的身份。

此轮验收覆盖宿主 xypm 候选盘事务和客体运行。客体内 glibc xypm 自身的维护事务、
默认切换、newlib 退役与动态链接各有后续验收项。

```sh
python3 scripts/create_xypm_profile.py create --runtime-family glibc --cxx \
  --sdk-build "$XOS_GLIBC_CXX_SDK_BUILD" --id xos-x86_64-glibc-xpk-cxx-v1 \
  --output build/xypm_profiles/glibc_xpk.json
python3 tests/glibc_xpk_guest.py --system "$XOS_SYSTEM_BUILD" --dash "$XOS_DASH_ELF" \
  --dash-receipt "$XOS_DASH_RECEIPT" --sdk-build "$XOS_GLIBC_CXX_SDK_BUILD" \
  --profile build/xypm_profiles/glibc_xpk.json --output build/glibc_xpk
```

| 工件 | SHA-256 |
| --- | --- |
| 系统 `d82908b725ffd19a` manifest | `70f7ba2a3d9b1607269a73dbbc9a79278297819624539547a2114b444e42601c` |
| 系统 ISO | `64230b48317bb327fcac03651982381b98912da10a3256e98b73d7d3091fa1f5` |
| 系统 SDK manifest | `6a9137cd7127d0c0e35ea46f82b3031affc930b7da70555268b58a0ddd4fb0c1` |
| dash ELF | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| glibc C/C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| glibc C/C++ SDK 树 | `2070dbad9ddd860a11dd1511f1268c1f62683df01d1a967bfa741e53df0799d6` |
| 应用 profile | `5c4c478c52a2d9633365851f2a8849c3c758b11b926aa1c8f6b16ba318d385f7` |
| `build_glibc_program.py` | `44e3772c4350c5dc2ac9852413f1786f5877f390b0f6db7098af4ddc9fd2d135` |
| `xos_app.py` | `acc52a010150d59092bc570d6e33bc687de14dc2b4c58f908d21b37fbadcbdb4` |
| `glibc_xpk_guest.py` | `d3f78c7e749247948425ac1df8b5f9dc47c682e247d2667c8677bda2ce775bc0` |
| 生命周期回执 | `f8f6ddfb03c7df54cbab3bec9c74c98b98ef105bfe808f1cc0d67c7cc957d384` |
