# 9ed4bde7 · GNU rtld 固定闭包 TLS

基线 `da4a66b6`，沿用已验证的 XOS 首线程 TP 接管和私有早期堆。在 GNU
`dl_main` 既有位置使用相同的初始 TLS 分配和模板填充。GNU 分配 slotinfo、
按各模块的 `PT_TLS` 规定计算静态 TLS 偏移、建立 DTV，再安装主线程 TP。
模板填充仍通过 `_dl_add_to_slotinfo` 和 `_dl_allocate_tls_init`，保留代数、
对齐和复制规则。XOS 早期堆拒绝申请时，启动用原生诊断退出 127。

XOS 固定闭包从 self-relocation 完成后的 `_dl_start_final` 初始化
`_rtld_global_ro` 的原有函数指针。GNU 已在该位置写入另外两个入口，ELF
RELRO 此时仍可写。函数目标和结构保持一致。早期共享诊断的实际
`getpid`、输出和退出使用原生机制，从而在初始化 TLS 和文件描述符表前运行。
本阶段可使用真实 GNU 数据和真实 rtld support 对象链接验收探针，并避开尚未
可运行的完整解释器入口。

## 两个固定依赖

两份真实 GCC/binutils DSO 通过现有认证文件会话和同一打开实例验证 SHA-256 与
program headers，再按 SONAME 认领其只读 pin 并映射。每个对象的 `.tdata`
含 3 个非零字节，`PT_TLS.p_memsz` 为 145 字节，所需对齐分别是 64 和
256 字节。原生准备记录从实际映射程序头提供模板信息。真正的 GNU
`init_tls`、`_dl_assign_tls_modid`、`_dl_allocate_tls_init` 计算和写入
各 TLS 槽、清零尾部、递增 DTV 代数为 1。调度让出执行后生产 NPTL 安装的 TP
和已更新的 DTV 保持可用。

错误用例将真实私有堆限制为两页，然后让 GNU 最小分配器成功取得两个块。
剩余不足以容纳实际 slotinfo，`init_tls` 使用原生诊断退出 127。下一次
普通进程以写权限打开并关闭同样两个文件作为 pin 回收对照，然后再次验证
只读映射和 TLS。两个用例退出后的空闲页、任务和完成记录均为
`129696 / 3 / 1`。

`c4bb45c7` 的两模块原生验收在 QEMU 11.1.3 得到 `passed_subset`。

| 验收输入 | 标识 |
| --- | --- |
| 原生 ISO `f141fdb9c91847b8` | `8bfc2cb8be148ab659501f9c23572f5de31188ccb95bdbd2055b7386931ad99f` |
| glibc C SDK 清单 | `3fa2bd497b352957d67b9fe8ea1954ac50653a314e55e6471708cbb00c233ee5` |
| SDK profile | `6c27c745cc79d848fef3ff228255aa3f1b27c6c8fedde37d96571a247de54e48` |
| GNU 共享 rtld 清单 | `a636e48a23524552a25b305b59b924f24f9ebe3f92a163d34f4918cb5c86c150` |
| 两模块原生探针 ELF | `46d589b60df2530d4e9d54bfcddf4a512b173ec288f88e46865f7e94632c5a89` |

## 共享 libc 的 errno 叶子

`d30345ee` 加入由实际 GNU 共享 libc 规则编译的 `csu/errno-loc.os` 和
`csu/errno.os`。测试 ELF 的自身 `PT_TLS` 作为 GNU 初始布局的第一模块，
两个依赖是第二和第三模块。GNU ld 在探针入口的 ELF 链接中将 errno 的
initial-exec 寻址解析为 `FS:0 - 4`。在早期堆封存后，该真实 accessor 的返回
地址与 DTV 第一槽一致，初始值为零。写入后通过原生定时调度，重新调用 accessor
仍读到同一个地址和值，同时保留两个 DSO 槽。精确绑定在 QEMU 得到
`passed_subset`，普通路径退出 0，真实私有堆预算不足退出 127，两次均恢复
`129696 / 3 / 1`。

| 验收输入 | 标识 |
| --- | --- |
| 原生 ISO `9ff4810e34352c67` | `25ac9609639e5582a24a3b7437202b08ebbfcdde92909ef0804a4a862fccec8a` |
| GNU 共享 rtld 及 libc 叶子清单 | `00ae5b844e4d9516f80d9851a14285c2d1d501642729472e6c6a74cdfcda7e29` |
| 三模块原生探针 ELF | `002ce96e6c56675de396c17beffaff540bd3dc06630d461aa435ae215c07adf1` |

公开 ABI 文档检查通过。对比基线，静态 `getpid.o`、`libc-tls.o`、
`dl-tls_init_tp.o` 和 `dl-printf.o` 的代码段逐字相同。
`build/d1_rtld_closure_tls` 保存两次验收的原始日志、回执与快照。解包
`system-late.tar.zst`、`glibc-c.tar.zst` 与 `rtld-late.tar.zst`，
以 `--system`、`--sdk-build`、`--rtld-proof` 和目录内的
`--profile` 绑定输入，再指定新的 `--output` 运行
`tests/glibc_d1_closure_tls_guest.py`。还原回放再次通过，探针 ELF 和
两个 DSO 的哈希相同。旧首线程接管、解释器准备与早期堆、固定依赖映射
三套验收在同一新 ISO 和 SDK 上回归通过。

## 完整解释器边界

当前 `dl-sysdep.c` 仍阻止完整解释器构建。完整的 `libc.so` 交接须使用真实
GNU 动态重定位及 `_dl_call_libc_early_init`。共享构建的真实
`errno-loc.os` 与 `errno.os` 组合为独立 DSO 时产生一项 ELF
`R_X86_64_TPOFF64`，目标指向 libc errno 槽。普通动态装载这一对象仍需要实际
完成该 relocation，其他共享 libc 初始化、工作线程 TLS 与 D2 生命周期也需
原生验收。

## 合入初始线程后的组合复验

`98ee1f22` 在 #291 上接入独立早期堆期限，固定两个 GNU 夹具的编译输入与摘要。用签名
C SDK 和真实 GNU 对象重建系统 `97cce681943c3eb2`。QEMU 中首线程门两轮通过，固定
依赖门的普通布局及堆容量不足两条路径通过，均回到 `129709 / 3 / 1`。ABI 对照通过。
[组合回执](../reports/glibc_d1_fixed_closure_post291_20261126/manifest.json)

## #289 合入后的主线复验

固定闭包提交按原顺序重放到 `312a2905`，签名 C SDK、GNU 目标和系统
`97abed18e6d772eb` 从提交 `b13ef5be` 的源码归档重建。首线程两轮及依赖
闭包正常和堆不足路径均通过。#289 合入后，确认 `92d1e02b` 是主线
`d7c56292` 与该闭包的实际合并树。此间唯一改变系统输入清单的文件是应用矩阵
测试，glibc SDK 和 GNU 探针输入与原次相同。用相同验签 SDK 和 GNU 对象为
合并树重建正常系统 `6a60f841fb3ae2fb`，再次跑过两项原生门禁。普通进程退出
0，真实早期堆不足退出 127，其后两个依赖均可重开写端；四轮资源均回到
`129696 / 3 / 1`。新系统和原始串口摘要见[主线复验回执](../reports/glibc_d1_fixed_closure_post289_20261126/manifest.json)。
