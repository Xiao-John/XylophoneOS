# 0066：xypm P2只读计划与部分客体验收

2026-10-27。独立工作区`codex/xypm-p2-p3`，基线655b128。用户要求完成P2验收、
拆分P3网络依赖并实施可离线部分；本记录是进度交接，P2及P3离线部分均未完成。

## 实现与发现

- `src/user/programs/xypm.cpp`：修复冻结SDK中不支持的`%zu`/`%lld`格式用法；加入
  安装后的包数/文件数上限预检，以及`plan remove <id>`的归属文件和反向依赖预检。
- `src/user/programs/xypm_native.hpp`：JSON节点分配按类型要求对齐。
- `tests/package_p2_verify_guest.py`：同一归档供宿主与客体验证，使用隔离FAT盘，
  检查计划、双Shell、损坏索引和被修改归属文件。新增代码Apache-2.0，无新依赖。
- `docs/plans/packages.md`：将P3拆成网络前可做与网络依赖工作；签名、密钥轮换和
  防回滚也可离线实现，可信时间及在线传输须各自验证，不能以摘要宣称身份认证。

首次客体运行中12个包样本与宿主一致，但安装计划打印`Files: zu`后发生页错误；
原因是现有运行库的格式化实现不支持当时使用的长度修饰符。失败报告与串口日志位于
`build/xypm_p2_p3/verify/`。修复后以不同目录保留最终证据，没有覆盖首次失败。

## 实际证据

GCC/G++ 16.2.0、QEMU 11.1.2、Python 3.12.15；冻结profile
`xos-x86_64-static-single-b2-v1`和原工作区的已登记single_b2_v1 SDK。实际命令：

```sh
python3 scripts/build_xypm.py --sdk /Users/xylo/Documents/XylophoneOS/.cache/xos_seed/xypm_sdk/single_b2_v1 --profile config/package/xos_x86_64_static_single_b2_v1.json
python3 scripts/build.py --output-dir build/xypm_p2_p3/remove_plan_system
python3 tests/package_p2_verify_guest.py --system build/xypm_p2_p3/remove_plan_system --xypm-build .cache/xos_seed/xypm/a985e65ceddde1d1da90/manifest.json --dash-elf /Users/xylo/Documents/XylophoneOS/.cache/xos_seed/dash/8098a3cc28ff4ce74f5b/build/src/dash --dash-sha256 a730086417e2d3f7204824c9dd1f6ac25cac61e3b0fd59747315fcba72e11646 --output build/xypm_p2_p3/qualification
python3 tests/package_p2_maintenance.py --system build/xypm_p2_p3/remove_plan_system --output build/xypm_p2_p3/remove_plan_maintenance
python3 scripts/license_audit.py --build build/xypm_p2_p3/remove_plan_system
git diff --check
```

系统build `adc8567560248916`、xos.img SHA-256
`0e6bef8e867ba02834c166c5617b08b81480d4dee94ea3d69ad17d20b7142fe4`；xypm包SHA-256
`5933994bb42c866c2be5e848609d2da99415006d2697daa2ca29804a23e4a08b`，ELF SHA-256
`26df8cf07049d523746727792a9da8ec6626ffdae9a3d9efec85996600a372db`。
`qualification/verify_report.json`记录17个相同包输入的宿主/客体一致结果，另有6个计划
输入及17项计划、
冲突、数据库、xsh/dash及重定向检查；资源回到`[130322,2,0]`。
`remove_plan_maintenance/maintenance_report.json`为当前系统的维护门控9/9，资源相同。
许可材料检查7份通过；预构建库逐成员许可审计仍未完成。

## 未完成与接续

P2-2尚缺全边界/真实FAT短名别名与更多损坏数据库客体差分，未宣布gate关闭。
P2-3持久日志、stage/backup、开机恢复门禁与P2-4安装/升级/移除/恢复均未实现，
进程中止各步、提交前后重启、幂等恢复、满盘、损坏日志等也未验；没有掉电或撕裂
扇区保证。当前`maint-recover`仅凭指定worker成功退出释放门禁，不可当作已完成的
持久恢复策略。恢复工具还须在xypm本身升级中断导致文件缺失时可启动。

P3离线索引/锁文件、签名/可信根和密钥轮换等均未实现或验收；网络及可信时间能力
各有独立前置。下一步先完成P2-2剩余对照，然后实施可持久恢复的P2-3/4并按计划
逐步故障和正常sync重启验收；P2通过后实现P3离线部分。其他工作区的supervisor
改动尚需在整合时核对，未将其未提交改动纳入本工作区或覆盖。

## 接续：清单差异与P2-3启动门禁

用户继续要求推进。新差分样本复现客体误拒400个中文字符的合法版本字段，失败记录
`build/xypm_p2_p3/metadata_difference/`；客体字符串长度现在按Unicode字符计数，
许可和构建回执路径须与文件清单的原始大小写一致。随后`gate_verify/verify_report.json`
记录20个包样本与6个计划输入的宿主/客体结果、17项计划与双Shell检查；仍未覆盖所有边界。

`src/user/programs/supervisor.cpp`新增恢复标记门禁：启动前检查
`/var/lib/xypm/transaction`，存在或无法确认不存在时限制普通启动/写命令；维护
worker退出0后再次检查，标记仍在或检查失败则保留准入屏障。已在隔离FAT盘使用合成
标记检查重启、普通进程/写操作阻止、成功worker不能凭退出码解锁、标记清除后释放、
新worker创建标记及不可读盘失败关闭。该探针清除的是空的合成目录，不是包恢复器。

最终系统build `77a2dbf0d25f3e0a`，xos.img SHA-256
`c56bbca91a9453c0ce468a80e86781fb9cac6c39275d11e3e957d7cb9829d452`；xypm包SHA-256
`462505c0ea6a31d17f09d294b4ad410226eb46683528c5ded21f47bd20a34d5c`，ELF SHA-256
`82b3e08f83971fa8aa0d23b8e0da3858f3925188dc9c50b84f9197ea3eb00c3b`。
`gate_unreadable/gate_report.json` 7/7，`gate_maintenance/maintenance_report.json` 9/9，
资源回到`[130322,2,0]`；许可材料7份通过。测试使用独立盘和系统，未更新发行资产。

```sh
python3 scripts/build.py --output-dir build/xypm_p2_p3/gate_system
python3 tests/package_p2_verify_guest.py --system build/xypm_p2_p3/gate_system --xypm-build .cache/xos_seed/xypm/0601dc9ae635c0fdbeb4/manifest.json --dash-elf /Users/xylo/Documents/XylophoneOS/.cache/xos_seed/dash/8098a3cc28ff4ce74f5b/build/src/dash --dash-sha256 a730086417e2d3f7204824c9dd1f6ac25cac61e3b0fd59747315fcba72e11646 --output build/xypm_p2_p3/gate_verify
python3 tests/package_p2_maintenance.py --system build/xypm_p2_p3/gate_system --output build/xypm_p2_p3/gate_maintenance
python3 tests/package_p2_persistent_gate.py --system build/xypm_p2_p3/gate_system --output build/xypm_p2_p3/gate_unreadable
python3 scripts/license_audit.py --build build/xypm_p2_p3/gate_system
```

P2-3现已开始，但上面的“未实现”对实际journal、备份、受损日志与可独立启动的
恢复工具仍成立；P2-4写命令及每步故障/重启验收仍未开始。另一工作区的supervisor
也有未提交编辑，整合本分支时须保留并合并两方改动，不将此系统证据用于合并后源码。

## 接续：P2客体事务与启动恢复

已实现受维护租约约束的`install`、`upgrade`、`remove`、`recover`，事务准备、
旧文件备份、新文件stage、校验绑定的journal、commit和清尾。验证及stage使用同一个
已打开包文件；提交前失败使用旧文件回滚，提交后清理；不删除非空的用户目录。
恢复器作为系统内置模块加载，磁盘上的xypm因自身升级中断而缺失时仍可运行。
监督器检查三个持久路径并在异常或无法检查时保留准入门禁。损坏journal、备份、
commit或被外部修改的目标会保留材料并阻止自动恢复。

构建`bbd9ee9c5020d549`（xos.img SHA-256
`7ee07c422aa0134050f2ec816c3c98dd0f85bdafb0f9e004f422d733a13f6733`）及
xypm包`1a80ddb7f25430abb0302f83314796cacf0cd8de766fcccbbd338d37739cd272`：
真实安装/升级/移除、重启、摘要拒绝、用户文件保留通过8项；恢复正常及损坏材料
11项通过；维护门禁9项和持久标记7项通过。满盘测试将空闲空间压到1 MiB，升级
失败后经内置恢复器清理，宿主确认原安装包及用户数据完整。自身升级测试通过正常
升级、xypm文件缺失时启动恢复和重新升级。恢复器的逐点中断首轮17/17通过。
安装事务上一构建34/34中断点通过；当前构建安装、升级、移除逐点回归仍在执行。
这些是进程终止及同步重启证据，未验证突然掉电、介质写入失败的所有位置或扇区撕裂。
完整清单边界和真实FAT短名别名场景仍不能以现有样本穷尽。许可材料检查7项通过，
预构建库逐成员许可审计未完成。最终验收须以包含所有测试源码的最终系统构建重跑，
此前记录的“未实现”是当时状态，不代表当前实现。

## 最终源码构建的P2验收

系统`17c791d44a662629`，xos.img SHA-256
`cd08748c31473e849a66f5e3ce773280b3aad32db793a5886bb01fb313b338e9`；
正式xypm包`1a80ddb7f25430abb0302f83314796cacf0cd8de766fcccbbd338d37739cd272`，
ELF `391320830a4f2a45961878e19295a006242eb5d627b8f0b66aaa70fd04e9f05d`。
测试在独立FAT盘与QEMU中执行，不修改日常盘：

- `p2_final_verify/verify_report.json`：21个包输入与6个计划输入宿主/客体一致，
  18项计划、双Shell、交互式dash退出后维护升级及数据库错误检查通过。
- `p2_final_transactions/transaction_report.json`：真实安装、升级、移除、重启、
  用户文件保留和摘要约束8项通过；`p2_final_full_disk/full_disk_report.json`：
  1 MiB剩余空间下升级失败，恢复后旧包及用户文件保全。
- `p2_final_recovery/recovery_report.json`：恢复及损坏材料11项通过；
  `p2_final_recovery_fault/recovery_fault_report.json`：恢复回滚9/9、提交清尾8/8
  个中断点可再次重启恢复；`p2_final_self_upgrade/self_upgrade_report.json`：自身
  升级时xypm缺失后使用内置恢复器恢复并成功重试。
- `acceptance_fault_install/fault_report.json`、`acceptance_fault_upgrade/fault_report.json`、
  `acceptance_fault_remove/fault_report.json`：安装34/34、升级45/45、移除36/36个
  事务检查点中断后重启恢复；逐步回读数据库、文件和用户数据。
- `p2_final_maintenance/maintenance_report.json`9/9，`p2_final_gate/gate_report.json`
  7/7；`license_report.json`许可材料7项通过，预构建库逐成员审计仍开放。
- `p2_final_real_alias/alias_report.json`：真实FAT的`LONGDI~1`可访问长目录中的
  标记文件，含该别名路径的包被宿主和客体拒绝；脚本保存在
  `build/xypm_p2_p3/real_alias_test.py`。该例验证短名语法被拒绝，不代表穷举全部FAT
  名称组合。首次因等待旧提示符而失败的日志保存在同目录`first_failed.log`。

并发执行时一次安装中断回归因串口计数行尚未接收完整而失败，保存在
`final_fault_install/`；修正测试等待整行后，以最终系统重新跑全点通过。这里的
中断注入发生在代码定义的检查点并执行sync，不等同于任意指令时刻故障或突然断电；
设备缓存丢失、扇区撕裂、所有介质I/O错误和超大事务第二段空间预留尚未实测。
有限畸形输入也不构成对所有可能归档的证明。以上范围内P2实现和验收完成；P3离线
部分尚未实现，且本工作区的supervisor须与主工作区未提交修改人工合并后重新验收。
