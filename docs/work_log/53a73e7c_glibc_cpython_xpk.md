# 53a73e7c · 可安装的 glibc CPython 核心与标准库

从已验收 CLI 的 `591a2617` 创建独立工作树。用同一 glibc 2.44 C/C++
SDK 和 `xos-x86_64-glibc-cpython-package-preview-v1` 构建 CPython 3.14.9
与原生 xypm。profile 通过现有 SDK 完整绑定和源码签名证据验收，以
`directories`、`threads` 明示候选依赖。v1 XPK 和 native P2 使用现有路径。

XPK 包含 `/usr/bin/python3`、`/usr/lib/python314.zip`、标准库前缀定位文件、
许可和构建回执，共 14 个外层文件，20,305,920 字节。静态库 ZIP 使用
stored 格式，包含既有 PY1 筛选规则选出的 558 个文件。标准库来自锁定源码
及实际构建补丁，回执逐一记录摘要。库不依赖 zlib。
运行 ELF 为 9,402,096 字节，完整调试 ELF 为 46,544,408 字节并保留。
剥离工具由 SDK 摘要绑定，校验程序头、LOAD 与 TLS，比较时只忽略 ELF
文件头中随调试节调整的节表位置、节数和节名索引。
[打包器](../../scripts/package_cpython_glibc.py) ·
[安装路径与命令](../plans/cpython.md#glibc-xpk-候选)

| 输入 | SHA-256 |
| --- | --- |
| 匹配的 C/C++ SDK manifest | `a9490cc126053b9e15808533e388f9d780ce0bc8e9b48ae71f3926932dfdfbdc` |
| profile 文件 | `b2d771e77c0f369b59f7fb6d246e4374843986487d34640e2a53621d064ceb21` |
| 原始解释器 | `3366bc916b623ce628f5b42a0bacc73bdfc618773f887e6c4e778f6800587a85` |
| 包内的运行解释器 | `af5291a1ece7482efd182e72add28bd5f7833e9192a2cdb1d6be2d1fc021e3a5` |
| 同 profile 的 xypm ELF | `deb46c1f32bd34cf36996d6334b02280dab9775798a0031e36a7428a9e7755e2` |
| 可安装 XPK | `c50cc2684dbc810cb093ad5408fa7caf9f326a73ba09388881c5ff52c01755ac` |
| 正常系统 `4a2034af1c36be0c` ISO | `ed236155b1a2229d4c1614bdc445e1a76b2b42f5fac9c0daec1c8888673e8005` |

宿主 XPK 安装预检在真实 QEMU 中运行安装盘上的解释器。模块来源检查确定
JSON、argparse、hashlib、pathlib、TOML、XML 和 zipfile 来自磁盘
`python314.zip`。既有 PY1/A1 的正常操作、时钟和线程测试通过，统计
模块执行结果为 `passed`，进程退出 0。保留静态 CPython 的
`Could not find platform dependent libraries <exec_prefix>` 提示，动态
模块路径没有可交付库。适用范围为实际测过的静态核心和库操作。

## 原生安装、运行与卸载

在正常系统的私有 FAT32 盘上从 XPK 实际安装。冻结 newlib profile 拒绝
该包。无维护租约的普通安装被拒绝，显式维护命令按预期摘要安装，既有
恢复程序完成事务清理。关机后核对 14 个受管理文件的摘要。

重启后使用 `exec-file /usr/bin/python3 -B /tests/stdlib.py` 启动实际
安装的解释器，验证磁盘模块来源、PY1/A1 的操作，及进程时钟、阻塞休眠
和原生线程。正常进程退出 0，缺失模块的脚本确实退出 1。原生卸载清除了
全部包文件、事务目录和已安装记录。安装前已有文件、Python 写出的 UTF-8
文本与 stored ZIP 在卸载后均保留并逐字节核对。拒绝、安装、正常运行、
错误退出、卸载后资源均恢复为 129795 个空闲页、2 个任务、0 个完成记录。
第二次使用完全相同输入打包得到逐字节相同的 XPK。

QEMU 11.1.3 原生验收回执 SHA-256 为
`6d13dd9bb6db675cbbb9282c11b5aa5dca5e337c25c53e6554506bfbd8f1e98c`。
[完整门禁](../../tests/cpython_glibc_xpk_guest.py)

## 正式构建入口修订后的复验

源码树 `3fddecc48b00b4c9f4b5f50055c9d8a3ccad2fd0` 组合主线 `cb14678a`、
已复验的 CPython 入口 `21d65680` 和包提交 `c765d44a`。以同一签名核验的
glibc C/C++ SDK 和同一 profile 从零构建宿主与目标 CPython，重新构建原生
xypm 并生成 XPK。静态标准库包含 558 个文件，包管理登记 14 个外层文件。
常规系统 `cb8c5a014430e979` 在 QEMU 11.1.3 复验五项。实际原生安装、重启
后读取磁盘标准库并运行原生线程、原生卸载及数据保留都通过。冻结 newlib
profile 与普通非维护安装继续拒绝该包。两次启动的资源基线均为
129795 个空闲页、2 个任务、0 个完成记录，检查结束后恢复原值。

| 复验工件 | SHA-256 |
| --- | --- |
| CPython 构建回执 | `5f60e24f9cf20e88564bbdf9deb5dfb93055a219c2701af23f4bc53f64e17b61` |
| 常规系统 manifest | `ab50d1925dce9163f54321a2709ecfd5077452b2ba91a0623af1a92500aa6cf0` |
| 常规系统 ISO | `dba5e88b021b3a948c8584f871614ba32356906bdb59033c12724c544ebe1557` |
| 原生 xypm ELF | `deb46c1f32bd34cf36996d6334b02280dab9775798a0031e36a7428a9e7755e2` |
| CPython XPK | `d8ab0a6e6e432a038b4675696f8ac2eb17f345309b751290995dc1cc4eb387ab` |
| 原生生命周期回执 | `ffec65f192ea1883a62a9a4272a0341a26f7f718033ad828d7393ce14f2dc800` |

## 源码快照与新版基线

在公开源码 `3fd45249dd0b4c2744551889c6efa8f8ea952021` 对应的 Git 树
`5cccb53e6924b25c9b102e89e32787747809ea25` 重建宿主与目标 CPython、原生 xypm
以及 XPK。打包器先把源码归档和补丁树复制到私有目录并核对副本摘要，然后从
同一副本生成 ZIP。使用错误摘要的归档时，打包器拒绝输入，且未输出 XPK。

常规系统 `f13306c98db13871` 在 QEMU 11.1.3 通过原生生命周期的全部五项：
冻结 newlib profile 拒绝、非维护安装拒绝、原生维护安装、重启后使用磁盘标准库，
以及卸载时保留用户文件和 Python 输出。XPK 包含 14 个托管文件和 558 个标准库
ZIP 成员。两次启动的资源均恢复到 `129795 / 2 / 0`，缺失模块仍退出 1。

| 复验工件 | SHA-256 |
| --- | --- |
| CPython 构建回执 | `0ddca71f8d233382cedfbe7b99994defd46fd5eb3eec4b8bea23e7aaa90917d1` |
| 系统 manifest | `283ba7e2487b6e526f90139bba1f6341c3e3b76001dfa9a588856183dadafac0` |
| 系统 ISO | `0173454215b58a562570386ed52f2f3cce518751ef97b371bf30d70753622b3e` |
| CPython XPK | `f3626102ea2d341d0c34fcd0375da7874a74def8aac2b7edf96fe1782b11b159` |
| 源归档拒绝日志 | `341d1321c573499e2ab40d0624662bcc2e4cccce350ac26b125663525c8d294f` |
| 原生生命周期回执 | `9dab7735961fbe7612daf10e05f89c6e3833571b6ca5cfc9b3144f0ad236ae02` |
