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

## ncursesw 串口组合

将已验收的终端 `select`、已锁定的 ncursesw 6.5 与 Unicode 标量补丁组合于
`2a31b409145ff28fd9fff6fcfd01e1aab8889cc7`，从干净的 SDK 和系统目录构建。
实际 ncurses 配置检测到 `select`，`poll` 保持未实现。QEMU 11.1.3 运行
原 W1 locale 测试、24×80 终端重入及宽屏测试，三项均退出 0。实测 Left、F1、
分片 CJK、无效序列后恢复、组合输入和有颜色的串口显示。三项结束时资源计数
均为 `129514 / 4 / 2`，终端服务在三项之间继续使用。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `27b469b7e3c35968` 清单 | `0fb5dc704f0948421be6e45ef71594175467474fbf7f13cc43be8d4d9c072fe6` |
| 系统 ISO | `ad502c5b9ba83bc1e96f33fdd56da82672c7e25feb344449b7c907d3cc8514e0` |
| 验签 SDK 清单 | `4242fb246959eb95cc231b9cea45b02e190e45db02ef0ad69eb8d59db28e1f58` |
| profile | `a4bf5a294f7f96238139c793982e090f90a761b393fcee13f8d2d0c29b3e6868` |
| 同源 `LC_CTYPE` | `40680545df4f92443c15e7c6f51a7fdc9154ebedd9eff1ed5c48437039add365` |
| W1 报告 | `77c80c7a2d6f7ef791899de8b06820bf1a3576e787f604f3e8a91818b2a7d604` |
| 串口 | `eb5d4bc39fbad716aeac8e62456d13f3e8a355e6bc995b7432172042cb770c2b` |

已绑定的安装证据另见[冷启动安装与事务清理](03c0fe80_install_bundle_before_audio.md)。
上述记录是各自源码与执行范围的验收。默认 SDK 切换、完整 C3、解释器链接与运行、
Pumpkin 生产部署和 ClarkE 完整引擎继续按[阶段计划](../plans/next_stage.md)验收。
