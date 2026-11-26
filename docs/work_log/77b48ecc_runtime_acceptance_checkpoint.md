# 77b48ecc · 运行库与来宾组合验收检查点

## 主线回归

分别从干净源码构建 `77b48ecc` 和 `39b4e51a`。macOS 的 QEMU 11.1.2
在系统 `845671e8ba8f92de` 上通过 `make smoke` 的 79 项运行检查、
10 项许可材料检查及 `tests/abi_doc_consistency.py`。Linux arm64 上以同源验签
glibc 静态 C SDK、同源 newlib dash 和更新的 glibc dash 构建系统
`b1648f01787feeea`，在 QEMU 11.1.3 通过路径变更 2 次、管道 2 次、
进程启动等待 6 次及两种 Shell 各 20 次的 glibc 检查。每组核对准确退出结果
与资源回收；双入口复核了工作盘产物和保留项。

| 工件 | SHA-256 |
| --- | --- |
| `77b48ecc` 系统清单 | `06f312fe6d9714e1a2f01260f0d0bbc0e878b4f70d1314ecedb5e9d677610893` |
| `77b48ecc` ISO | `b7b74fc43c28ee6ab9d320916a0cfae9351e06923e2412ef1cac1394db386537` |
| `77b48ecc` 常规日志 | `a45501cd4e7e18e9e9a52078a126b3b825c5baad4c00d0173313226af38e5b55` |
| `77b48ecc` ABI 日志 | `e2e4c52a0306922418b0917ef17cc47d9eba2bec406bbb9f4f1387b8c86eb301` |
| `39b4e51a` 系统清单 | `987029b2b1475124994466c6ffa8f77a579a9fc2d7a053ae8eba60c42e6f2016` |
| `39b4e51a` ISO | `6622799ce60ef459383ad4537056334fe1890988ba3aae419dda2d401e79103b` |
| `39b4e51a` 静态 SDK 清单 | `086980eaf0c99a53f96decce69b8705990d57a61933ea54cc70a3c8c620f3871` |
| `39b4e51a` glibc profile | `9f68cbc9459aaba8a60f55d40fa7267cb92077b26680d24a35593a79d827cdbd` |
| 双入口报告 | `cd6353673e06a7eaaa2c4e7c2813734186e13e71a895af504d201cca18c11ff3` |
| 路径变更报告 | `787fe39b2b798b144edadfc16cf8492567aaf694e1fa10bf4624057aa7e0c003` |
| 管道报告 | `5b64b0906b193e9e8d7e306dd86af61b108fbfc7bbb8b356cff30919f48f8235` |
| 进程报告 | `2fc5450b81a76b6601347ec174d2bce83ff89d778acd310e8636f7eb6a42bb7c` |

## glibc SDK 与 ncursesw 串口组合

[首次串口组合](2a31b409_glibc_ncurses_serial_combined.md)通过后，从已合入终端
`select`、Unicode 标量补丁和显式 `stdio_transfer` 构建支持的实际主线
`f9d6384d02914adf56ce50ccba146aedde093109` 重建普通系统和验签静态 SDK。
候选 profile 通过工具与接收对象绑定，宿主 profile 套件通过 45 项，普通镜像
通过 4 个 glibc G2 来宾用例。

同一主线和 SDK 重新构建 ncursesw 6.5，使用已锁定的 xterm terminfo 和同源
`C.utf8` 数据。QEMU 11.1.3 复跑原 W1 locale、24×80 重入和宽屏，三项均退出 0。
实测 Left、F1、分片 CJK、无效序列后恢复、组合输入和有颜色的串口显示。
三项结束时资源计数均为 `129514 / 4 / 2`。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `6017e0e9a94219b5` 清单 | `f5e2e65603b9422fde6171ee04dcedddde93cbafd3d80f4f2fe5492031aab766` |
| 系统 ISO | `9de3a1e5ddcb1f9bef78303e2f54d6b7cfbfebe98b52d1668553bccb7b03e092` |
| 验签 SDK 清单 | `18fae63e3fde74b85f03c4059c1a8f1755c76e76642c24eb6f3eaf086b1b222e` |
| 验签 SDK 归档 | `5e0f746dcfc794bbe4ab8271ac1f688c9c9eb061e25acf7df526bf9b0793f636` |
| profile | `c507851bc91a92f538815739c2d0ebb65c6168a9c02c6d367e071f66f8bec3ec` |
| profile 宿主日志 | `17c5ce7b7ffc9d9b32ad121248224a8b3441ae91b4eb7e5d27cd24c1db1bf49c` |
| glibc G2 报告 | `c0ff1e29263cd0fc8b244960f50705d7646a47a31fc925fba45e5610440bc2c2` |
| 同源 `LC_CTYPE` | `40680545df4f92443c15e7c6f51a7fdc9154ebedd9eff1ed5c48437039add365` |
| W1 报告 | `144db46583a35790f501efd6d07a1361ed9be201bf026b79e84072987952eeaa` |
| 串口 | `604bc125e8a256e3a100a216152355e357dabf7898165b1de1a83fad5ee77711` |

已绑定的安装证据另见[冷启动安装与事务清理](03c0fe80_install_bundle_before_audio.md)。
上述记录是各自源码与执行范围的验收。默认 SDK 切换、完整 C3、解释器链接与运行、
Pumpkin 生产部署和 ClarkE 完整引擎继续按[阶段计划](../plans/next_stage.md)验收。
