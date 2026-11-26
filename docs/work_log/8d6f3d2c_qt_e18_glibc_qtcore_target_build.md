# 8d6f3d2c — Qt E18 glibc QtCore target build

2026-11-26 · 源码 `ba011e0d` · 系统基线 `9f7a9a0f`。QtCore 6.8.3 使用隔离
glibc C/C++ SDK 编译。现有 `core_smoke.cpp` 与资源文件由同版本宿主 moc/rcc 处理，
然后使用目标 QtCore、glibc CRT 与静态库链接成 XOS ELF。

## 构建桥接

- 先重验候选 profile 及完整 sysroot，核对 C/C++ 编译器、汇编器、链接器和归档工具的
  实际字节。CMake 编译器检查执行真实目标链接。链接组加入候选绑定的
  `libxos_terminal.a`，解决 glibc 文件运行库的 `__xos_terminal_*` 实际引用。
- glibc 目标复用现有 QtBase 源锁、QtCore 平台及事件分发。专用增量补丁让 SHA-3
  使用 glibc 的 `endian.h`，并采用 Qt 已有的空所有者名称路径处理 XOS 缺少的
  passwd/group 接口。glibc 目标由 libc 提供调用和错误，旧 Qt 本地 POSIX shim
  只在原运行库路径编译。无公共 ABI 变更。
- 外部夹具使用 Qt 生成的工具链加入目标 Qt 查找根。构建树的包装模块还需要目标
  QtBase 源码中的 CMake helper。编译与链接继续使用候选头、CRT 和库。链接使用
  普通静态模式，保留链接警告。

## 复现

实测宿主为 Linux arm64，CMake 4.4.5、Ninja 1.13.2、x86-64 目标 GCC 16.2.0 和
binutils 2.47。宿主工具来自同一 QtBase 6.8.3 源包，以原生 CMake 构建
`host_tools`，QtGui、Widgets、网络、SQL、DBus、QtConcurrent 和测试关闭。初次
原生构建的 Qt 同步头文件步骤在 macOS bind mount 上报权限错误，改用 Linux 构建
容器内的文件系统后完成。目标构建也使用容器内的独立目录。

```sh
python3 src/ports/qt6/glibc/build_core.py \
  --archive "${QTBASE_ARCHIVE}" --sdk-build "${GLIBC_SDK_BUILD}" \
  --sdk-profile "${GLIBC_SDK_PROFILE}" --host-qt "${QT_HOST_BUILD}" \
  --output "${QT_XOS_BUILD}" --jobs 7
python3 scripts/build.py --output-dir build/qt_glibc/system_rebound
python3 tests/qt6_sdk_probe.py \
  --image build/qt_glibc/system_rebound/xos-install.iso \
  --payload "${QT_XOS_BUILD}/fixture/core_smoke.elf" \
  --marker QT_CORE_SMOKE_OK --report build/qt_glibc/guest_rebound.json
```

宿主与目标构建可以在 Linux 容器中运行。客体命令需要在运行 QEMU 的宿主读取目标
ELF 和系统镜像。构建回执绑定源包、profile、编译工具、QtCore 归档、ELF 和程序头。

## 结果和范围

旧候选 `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e`
用于桥接排查。其 ELF `e937db668daebb26b2619b1b77ebe1e64bbd12a90f1089ecbfe7cd85b9ff0d5a`
在独立 XOS 客体输出 `QT_CORE_SMOKE_OK`、退出 0，资源计数恢复。保留初次
链接缺少终端库、编译缺少字节序及用户组头文件的失败日志。

最新候选包含运行库组的并发分配器锁修复。候选完整树和 GCC 认证材料已通过既有
profile 校验。源归档、profile 与 manifest 分别绑定如下。

| 输入 | SHA-256 |
| --- | --- |
| QtBase 6.8.3 | `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80` |
| glibc C/C++ SDK 归档 | `b4d9d152ffb81c94ce8de28f2e3fbf8300102885d7e3a848ac5c55ab450953cc` |
| glibc C/C++ SDK manifest | `7eee04884a96ced6de12d20794af6809f544e3f15bc4e409b4197e58b1583d7a` |
| glibc C/C++ profile | `5dde8b7cd0a2e5fe9d0db892b81f88eeed36e2f72ba89826209acb013362b10a` |

最新候选在空目标目录构建并链接。旧 sysroot 配新 profile 的负向检查在输出目录创建前
拒绝。新 ELF 为静态 x86-64 ET_EXEC，含独立 RX、R、RW 段和 TLS 段。使用此源码
重新构建系统镜像后，QEMU 11.1.2 TCG 单核客体的直接入口输出 `QT_CORE_SMOKE_OK`、
退出 0，资源计数前后均为 `[129714, 3, 1]`。

| 复验产物 | SHA-256 |
| --- | --- |
| `libQt6Core.a` | `9a6f3970166e56d3162b6870fe04d699106cc6a98ef7325c2bad978076c19a7c` |
| `core_smoke.elf` | `da52164287007d82c3a16155f91439c7a3905c9bc8c5926e49ae04939d26ae88` |
| Qt 构建回执 | `191cdb33707a8594707e9ddd129b2f9d9fad521ddb688e34615f86471ec3236e` |
| XOS 镜像 `de2855ca5193cfce` | `2ca545840c9c03197be9b926d4289ebdc641a166997c5bd08469aff8839d9ee2` |
| 系统构建清单 | `edd2417079f0139eac3d95c4ac7a8d4ac084608f0709e95a587df15b445c6e2f` |
| 客体检查回执 | `6741e40ef84c8dd175da4a6db863ab1660f9665532868ffea1de9563e3487706` |

QtCore 链接仍显示 `access`、`chdir`、`getcwd`、`mkdir`、`rmdir`、
`chmod` 和 `flock` 等接口的明确未实现警告。已有测试只覆盖嵌入资源、QThread
信号及退出资源回收。磁盘临时文件、计时器独立触发、Dash 入口、完整 QtCore G03、
目标 Qt Declarative/G06、Qt Quick/G07 和静态分发均待验。

## QtCore 包选择复验

PR #185 复核发现 `QT_ADDITIONAL_PACKAGES_PREFIX_PATH` 可以让同版本的另一 Qt
包优先于刚构建的目标 Qt。构建脚本从子进程环境移除此变量，夹具配置显式绑定
`Qt6_DIR` 和 `Qt6Core_DIR`。链接前将 CMake 实际选中的 QtCore 归档路径与预期
文件核对。

用声明版本 6.8.3 的受控竞争 CMake 包复验，旧配置进入了竞争包并以预设诊断停止。
同一环境下，修正后的配置选择原目标 QtCore 归档。复用上文已构建归档重新编译并
链接夹具，得到与上表相同 SHA-256 的 ELF。使用上表镜像从 xsh 复跑，输出
`QT_CORE_SMOKE_OK`、退出 0，资源计数前后均为 `[129714, 3, 1]`。
本次客体回执 SHA-256 为
`0d3a2b14a9e3926e7b4416c18d780a432cd851b4b910d4c98977841615a57878`。
