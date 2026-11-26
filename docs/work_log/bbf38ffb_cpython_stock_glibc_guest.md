# bbf38ffb · 选定 glibc SDK 的 CPython 原生包复验

用 `bbf38ffb` 重建普通镜像 `30071d4a06866c78`。在断网 Linux arm64 容器中用签名 glibc 2.44 / GCC 16.2 C/C++ SDK 和 `xos-x86_64-glibc-stock-fork-v1` profile，从锁定的 CPython 3.14.9 归档构建静态解释器、xypm 和 XPK。原始解释器为三段 LOAD、含静态 TLS。XPK 内的解释器剥离调试节，保留对应原始 ELF 和剥离工具摘要。宿主构建移到区分大小写的 Linux 卷并以单作业恢复一次被系统终止的编译。本次客体测试盘使用独立的宿主存储目录。

## 包字节及既有配置对照

| 项目 | 旧 CPython 专用 profile | 选定 stock fork profile |
| --- | ---: | ---: |
| XPK 字节数 | 20,305,920 | 20,305,920 |
| 受管理文件数 | 14 | 14 |
| payload 字节数 | 20,287,554 | 20,287,605 |
| 静态解释器文件字节数 | 9,402,096 | 9,402,160 |
| 最大成员和磁盘标准库 ZIP 字节数 | 10,654,445 | 10,654,445 |

两份包的文件和父目录名逐项一致，磁盘标准库 ZIP 内容逐字节一致。受管理内容中仅解释器和构建回执字节不同。单文件、payload 和外层归档均低于客体验证的 64 MiB、256 MiB 和 277,884,928 B 上限。以客体测试的初始目录为准，两份包的事务预留均为 7,208,960 B。
[对照和完整清单](../reports/glibc_cpython_stock_g4_20261126/manifest.json)

## 写入异常、故障盘与恢复

首次维护安装日志记录 `transaction write failed`，退出后原测试程序清理了临时盘，根因仍待确定。

第二次使用同一镜像、包和 xypm。原生安装、重启运行磁盘标准库、时钟和线程探针、缺失模块退出均通过。卸载备份阶段 QEMU 停在 `io-error`，硬盘节点 `ide0-hd0` 报 `nospace`，CD-ROM 正常。已保留原盘。FAT 尚余 481,878,016 B，journal 和 applying 标记尚未发布，暂存区含完整旧解释器、定位文件和零长度 ZIP 备份。用有空间的宿主目录上的字节一致副本冷启动 `maint-recover-boot`，清除暂存并逐一核对 14 个已安装文件。数据库、原用户文件及 Python 生成的 UTF-8 文本和 ZIP 字节保持不变。随后从恢复盘的字节一致副本冷启动重试卸载，14 个受管理文件、事务标记与安装记录均清除，非受管理文件摘要不变。原故障盘、恢复盘和重试盘各自保留。
[真实宿主空间故障及复原盘回执](../reports/glibc_cpython_stock_g4_20261126/storage_failure_and_recovery.json)

另用同一系统和 XPK，在测试版 xypm 的检查点 9 同步中断。原盘只暂存了 2,048 B 的解释器头，尚无安装文件和已发布 journal。对副本冷启动恢复后暂存清空，原输入和用户文件字节不变。
[受控暂存中断回执](../reports/glibc_cpython_stock_g4_20261126/staging_checkpoint_recovery.json)

## 重新运行完整客体门禁

在有足够空间的独立宿主目录保存 FAT 盘，使用相同 ISO、XPK 和 xypm 重跑既有 `cpython_glibc_xpk_guest.py`。冻结 newlib profile 拒绝该包。普通安装命令被维护写租约拒绝，显式维护安装完成，停机核对全部 14 个受管理文件。重启后的解释器从磁盘加载 558 个成员的标准库 ZIP，时钟、线程和静态标准库夹具通过，缺失模块退出 1。原生卸载后清除全部受管理文件和事务状态，原用户文件、UTF-8 文本与 ZIP 内容仍可逐字节读回。两次启动的资源基线为 129806 空闲页、2 个任务、0 个完成记录。
[完整客体与读盘回执](../reports/glibc_cpython_stock_g4_20261126/report.json)

本次状态为 `passed_subset`。范围覆盖锁定静态解释器、磁盘标准库选集和原生安装及卸载。不同 CPython 版本升级、Pillow 等外部扩展、全量标准库与动态扩展各有独立门。

## 与当前主线的接口核对

以 `41c24a62` 核对构建、打包、xypm 和客体 runner，以上入口与 `bbf38ffb` 相同。期间 files 服务的改动在私有存储探针的租约选择分支，回执中的普通镜像关闭了该探针。主线 #300 在另一份签名 C SDK `e0016a3a…` 中验收了 `faccessat` 和 `readlink`。CPython 回执仍绑定开工时的 C/C++ SDK `d32a5c3b…` 和 profile `a7bf0f84…`，两项新接口由 #300 自己的 guest 回执覆盖。
[主线 libc 路径接口](ab3628db_glibc_canonical_path.md)
