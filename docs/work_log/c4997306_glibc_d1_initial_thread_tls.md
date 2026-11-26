# c4997306 · GNU rtld 首线程 TLS 交接

基线 `ed16bdfc`。D1 固定闭包按现有 [动态链接契约](../contracts/dynamic_linking_d0.md)
使用 GNU 静态 TLS 布局及 XOS 当前线程的 TP 安装。

## GNU 调用顺序与所有权

签名验证的 GNU glibc 2.44 中，`elf/dl-load.c` 及主映像程序头路径记录每个
`PT_TLS` 的模板地址、大小、对齐及第一个字节的偏移。`elf/rtld.c` 的
`init_tls` 先建立初始 slotinfo、计算静态偏移、分配 TCB 和 DTV，再保存
`dl_initial_dtv`、调用 `call_tls_init_tp`。初始块与 DTV 由早期分配器提供，
发布的引用跨越分配器切换继续有效。初始 DTV 由 GNU 单独识别，避免交给后来的
`realloc` 或 `free`。

`dl_main` 后续将启动模块写入 slotinfo，更新代数，再由
`_dl_allocate_tls_init(tcbp, true)` 把已映射模板复制到首线程的静态区域并清除
尾部 BSS。完成重定位后，GNU 才切换相关运行时入口与 allocator，并进入共享
libc 的早期初始化。共享 `csu/libc-start.c` 接受解释器已经安装的 TP，只有
静态启动会执行自己的 `ARCH_SETUP_TLS`。当前 XOS 共享 `pthread_create`
仍拒绝创建工作线程。

## 原生首线程

XOS 的 GNU 共享 `call_tls_init_tp` 走隐藏的 NPTL 入口。该入口仍然通过已有
`TLS_INIT_TP` 执行原生 sys35 当前线程安装；内核同时更新保存值和活动 FS
基址。真实 GNU `__tls_init_tp` 初始化线程描述符、栈链、TSD 和 join 状态。
sys41 给出的已安装 TP、TID 与本线程真实栈边界用于一致性检查和设置
`stackblock`、`stackblock_size`。安装或取数失败走原生控制台和进程退出，
启动前可以诊断失败。

该入口只作用于 GNU 共享解释器。静态启动、公开 ABI、公开 mmap 和
`dl-sysdep.c` 启动守卫沿用现有契约。

## 验收范围

`scripts/probe_glibc_rtld.py --initial-tp-fixture` 用 GNU 解释器编译参数生成
`rtld.os`、`dl-tls.os`、`dl-tls_init_tp.os` 和探针对象。探针链接真实
GNU 的可写运行时状态、NPTL 初始化、锁函数指针和早期分配器。原生探针使用
签名 SDK 的入口符号，解释器入口在该链接中局部化。无需完整静态 libc、伪造的
运行时回调或外部未解析依赖。

探针在原生堆准备 TCB 和测试 DTV，再调用真实 GNU/XOS 的首线程入口。QEMU
验证内核保存的 TP 与 FS 实际一致，TID 与栈边界来自本线程，GNU NPTL
完成同一描述符的初始化。通过原生定时让出执行后仍能读取同一 TCB、DTV 和保活
数据，进程退出时由内核回收。探针的 DTV 测试项由 fixture 提供，真正的闭包
模块布局及 `.tdata/.tbss`、动态 libc `errno` 和 worker TLS 留待后续验收。

确切源码 `1b4d4771` 的探针在 QEMU 11.1.3 下得到 `passed_subset`。
两次从磁盘启动的独立进程均退出 0，每次结束时的空闲物理页、任务和完成记录
都回到 `129696 / 3 / 1`。公开 ABI 文档检查通过。比较基线与新构建，两份静态
`libc-tls.o` 与 `dl-tls_init_tp.o` 的代码段逐字节一致。

| 验收输入 | 标识 |
| --- | --- |
| 原生 ISO `b088c75e15870904` | `75620835f29435a34bd52a064d8db3b8b95a513aa846a85ca38f97c652101544` |
| glibc C SDK 清单 | `29f1d3af9b9fd0f88f5b032cf1541c204e42de5ea085b7b2f9ce44dfba719fa2` |
| SDK profile | `51f221ddf61a2c823b496b241523e5a9d3b6760ddbf636ab3c8e3ce948d91b3d` |
| 共享 rtld 探针清单 | `1ec82ee44ccf471799ee68f1d3e04d2523d8bebbe81952e843a822613221836b` |
| 真实 GNU `dl-tls_init_tp.os` | `b4d8492d4708696e00cc9237d5a142089a84a27e00b6839791e105b6b28e4a66` |
| 原生探针 ELF | `e60287ebb6ec26ae945f79a7dece115a850f833e988eb5b71d78139b5d8fda21` |

在 `build/d1_rtld_dynamic_tls` 本地保留系统、签名 SDK 和共享对象快照，以及
ELF、串口日志和回执。还原快照后运行 `tests/glibc_d1_initial_tp_guest.py`，以
`--system`、`--sdk-build`、`--profile`、`--rtld-proof` 绑定输入，
再指定独立的 `--output`。从归档还原的回放再次通过，并得到 SHA-256 相同
的探针 ELF。原有解释器准备、早期堆与依赖映射两套原生验收也在相同输入上通过。

完整的 GNU 初始 TLS 仍需组合映射与真实重定位。目标对象已经编译，完整初始 TLS
将保留 GNU 的 slotinfo/DTV 布局，并须在私有堆的预算拒绝路径检查 slotinfo
分配失败。系统启动守卫继续拒绝构建完整解释器。

## 与必需早期堆组合

当前早期堆契约把单调期限收进计划本身。旧 fixture 在上层合成后无法编译，已按实际
入口更新。`649e6719` 以 #287 和待审早期堆为输入，从签名源重建 C SDK、GNU 对象和
普通镜像 `93ae2e89d70c1ad4`。两次 QEMU 11.1.3 原生运行均核对 GNU TCB、内核
TID、真实栈范围及调度后的 DTV，并各自恢复到 `129709 / 3 / 1`。ABI 对照通过。
[组合证据](../reports/glibc_d1_initial_thread_rebound_20261126/manifest.json)

## #284 合入后的普通镜像复验

`1401b0e6` 从含 #284 和 #286 的主线重建签名 C SDK、真实 GNU 对象与普通镜像
`57db0fc06db3b7b1`。QEMU 11.1.3 两次启动验证 GNU TCB、原生 TID、真实栈范围和
调度后的 DTV，每次均恢复到 `129709 / 3 / 1`。ABI 对照通过。
[主线复验](../reports/glibc_d1_initial_thread_post284_20261126/manifest.json)

## 与原生 dash fork 的组合

`242edd5c` 在包含 #290 的主线上重建签名 C SDK、GNU rtld 对象与普通镜像
`ebebcc8cb9915707`。探针从私有冻结副本编译并取摘要，核对仓库夹具与编译输入一致。
两次真实 QEMU 运行通过 GNU TCB、内核 TID、真实栈边界和调度后 DTV 校验，每次回到
`129709 / 3 / 1`，ABI 对照通过。
[合成回执](../reports/glibc_d1_initial_thread_post290_20261126/manifest.json)
