# 12d22dce · 选用 glibc SDK 的安装介质

`build_candidate.py` 新增显式的 `--glibc-app-kit`，以已部署 kit 的 C/C++ SDK
和 profile 构建安装 dash。组装后重核 kit 全树，检查 dash 回执绑定相同 profile
和 SDK，并将实际安装 ISO 和客体回执写入候选清单。默认候选路径及操作系统
自举继续使用既有 newlib 输入。
[使用方法](../contracts/xypm_sdk_profiles.md#独立部署-glibc-应用-sdk)

## 首次外部启动

初始候选 `6e7c97a2040ff325` 在原安装门能运行 dash 内建命令。用该镜像的
已安装 dash 执行 C XPK 时，首个外部子进程实际收到 `EAGAIN`，dash 退出 126。
普通系统 79 项 smoke 当时通过。四个启动演示仍占用进程槽，需要在安装候选的
监督进程启用既有 `--quiet-demos-on-launch`，并在运行通用 smoke 时复用同一
系统工件。
[初始失败回执](../reports/glibc_selected_installer_20261126/before_fix_app_replay.json)
[初始失败串口](../reports/glibc_selected_installer_20261126/before_fix_installer_apps.serial.log.gz)

安装门新增一个系统构建清单所绑定的真实 ELF。新盘从安装 ISO 启动后，
在首个 dash 脚本中执行该 ELF，检查应用输出、脚本继续运行和退出 0。
该操作之后再运行原有的 PATH、交互命令和 ISO 目录检查。

## 验收入口

在 Linux arm64 的配套交叉工具链容器中断网构建，使用 QEMU 11.1.3
从新盘启动安装 ISO，五项检查全部通过。系统 `f2c15ccda70d7ae3`、候选
1,826 项源码摘要及 295 项工件摘要均重新核对。
[候选回执](../reports/glibc_selected_installer_20261126/candidate_binding.json)
[安装回执](../reports/glibc_selected_installer_20261126/installer_guest_report.json)
[安装串口](../reports/glibc_selected_installer_20261126/installer_smoke.serial.log.gz)

同一安装 ISO 在锁定的 QEMU 11.1.2 上从另一块盘启动。由 ISO 安装的 dash
分别从 PATH 和绝对路径运行已离线安装的 glibc C/C++ XPK。C 读取用户文件，
C++ 执行容器、线程 join 和异常处理。首轮自动回收四个启动演示及 44 页，
再从 xsh 直接运行 C 后仍保持 128880 空闲页、3 个任务和 1 个完成记录。
停止虚拟机后从工作盘导出的 dash 摘要与 ISO 负载一致。
[组合回执](../reports/glibc_selected_installer_20261126/installer_apps.json)
[组合串口](../reports/glibc_selected_installer_20261126/installer_apps.serial.log.gz)

同步保存的同一 Linux 构建普通系统，用 macOS 上锁定的 QEMU 11.1.2 执行
`make -o build smoke`，避免重建被测镜像。79 项通用检查及 10 项许可材料
通过，开放项为零。Linux 容器的 QEMU 11.1.3 通过安装检查，通用内核门继续
要求仓库锁定的 11.1.2。
[通用检查日志](../reports/glibc_selected_installer_20261126/ordinary_smoke.log)

## 默认切换余项

GNU Make 的目标构建仍依赖 newlib，CPython 和 xypm 的 glibc 路径仍各自需要
显式 profile。现有发行打包器继续消费冻结的 legacy seed 和 SDK。将这些
入口切入正式应用默认前，还须在最终组合运行存量程序和原生包事务，
并核对发行材料与回退入口。
[glibc 迁移门](../plans/glibc_port_scout.md#从加固期走向默认切换的门)
