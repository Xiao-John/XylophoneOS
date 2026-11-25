# 0c4c263f — glibc G3-T 静态线程与私有同步

日期：2026-11-25。实现起点：G1 主线整合 PR #149，
`6a463517bfa0d4d183c9107578c0ce582d6ed2d1`。现依赖 G2 完整静态 SDK
`4301925`，以及 `68fb020` 的干净构建/console 修复、`eb714bd` 的顺序安装
和 `0b28799` 的生成头依赖修复。本组与 G3-F 文件后端分别提交 PR。
使用用户指定的 `xos-glibc-sdk-preview` 工具环境。

## 修改与审计发现

1. 既有 cancelable futex 入口直接 trap，普通 `pthread_cond_wait` 和 `sem_wait`
   会走入该路径。候选继续显式拒绝 `pthread_cancel`，新增异步取消模式拒绝；
   在没有可接受取消请求的 profile 下复用私有等待，保留同步算法。
2. 补上 `CLOCK_REALTIME` 绝对期限转换，保持已有 `CLOCK_MONOTONIC` 路径；实际
   timeout 后重查实时钟，防止采样/抢占导致提前超时。修正负秒数加非法纳秒时的
   校验顺序，有限期限不会落入无限 sentinel。
3. 上游 `pthread_gettid_np`、`pthread_getattr_np` 将句柄解引用为 TCB，与当前公开
   原生 TID 身份不兼容。改为有锁的固定容量元数据快照；当前主线程的 stack bounds
   来自原生 thread_info。线程停止前清除条目；失败查询保持输出。
4. 上游 process-shared/robust/PI 属性设置原本成功，之后会进入未实现等待路径。
   在属性入口明确返回 `ENOTSUP` 并保留对象；非法枚举返回 `EINVAL`。
5. 新公共 API 客体探针覆盖真实 TLS/errno、TSD 析构、once、互斥锁/条件变量、
   semaphore、读写锁、barrier、64 位 join 值、`pthread_exit`、线程配额、属性
   查询及两个时间域的有界等待。该源码只通过候选 glibc SDK 链接。
6. TLS/TSD/libc 清理后的线程计数递减改为 release，供 G2 正常退出入口 acquire
   判断安全收尾。活跃工作线程持有 libc 锁时，G2 实施原生诊断与状态 127 的受控
   终止；其正常回调/flush 仍属实现缺口。另备有 stdout 持锁退出和主线程
   `pthread_exit`/最后工作线程 atexit 的独立客体探针。
7. 实际公共 pthread 链接暴露既有 `pthread_create` 引用了未构建 resolver 的
   `__libc_resp`。当前 XOS 配置没有 inet/resolv 子目录，移除该不存在组件的初始化，
   保留未来 resolver 移植时补齐每线程状态的明确责任。
8. detached 探针交替使用创建属性和运行中 detach，16 轮验证拒绝 join、TSD/TLS
   清理、TID 不复用及线程槽/内核栈页回收；等待采用公开单调钟的每轮 2 秒上限。
   原生 sys50 仅用于观察真实资源，线程行为全部通过公开 pthread/sem 接口触发。
9. 实际客体的 errno 隔离检查发现通用 `getpagesize` 存根经由属性初始化污染 errno；
   G2 按原生 ABI 实现 4096 字节页查询后，原测试通过。保留原 errno 断言。
10. 增加两层 `pthread_cleanup_push`，在真实 `pthread_exit` 路径验证 LIFO 顺序、
    TLS 仍有效以及 cleanup 先于 TSD 析构。

接口行为见 [glibc 静态线程候选 profile](../contracts/glibc_static_threads.md)。
没有新增内核 syscall、共享结构或 newlib 依赖。G2 的 sys35 主线程 TP 工作由另一
模块负责，本 PR 依赖其完成真实 glibc 主线程初始化。

## 输入和环境

- SDK release：`xos-glibc-sdk-preview`，镜像 SHA-256
  `22c851b6274a62ff1e31fd78089aea611142e92af27698018ffc1dda1e134009`。
- preview 工具：交叉 GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、
  QEMU 11.1.3；该 QEMU 是 preview 版本，区别于项目旧锁 11.1.2。
- glibc 2.44 候选归档 SHA-256
  `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`。
  源锁仍保持 `candidate_unverified_signature` 和研究用途。
- 宿主边界检查使用 GCC 14.2.0；ASan/UBSan 开启致命错误，LSan 因执行环境约束未运行。

## 已执行检查

```sh
python3 tests/glibc_g3_wait_test.py --sanitize
python3 tests/glibc_g1_futex_internal_test.py
python3 tests/glibc_g1_thread_name_test.py
python3 tests/glibc_g3_attributes_test.py --archive "$GLIBC_ARCHIVE" --sanitize
```

上述四项全部通过；preview 容器中的宿主 GCC 16.2.0 也运行了相同的四组检查。
等待测试编译生产转换代码，
仅以测试宏注入原生时钟/等待返回值，覆盖截止溢出、过去时间、非法纳秒、时钟故障、
value changed、errno 保持以及实际超时后的重新采样。futex 检查覆盖私有双时钟分派
和共享/PI/意外错误的失败路径。名称/属性检查覆盖容量、继承、detach 快照、退出
删除和过期句柄。

属性宿主测试从散列锁定的上游归档取出真实内部类型声明；宿主公共头仍用于该
隔离测试。候选完整头文件、目标 ABI 和真实调度行为以目标构建与客体检查为准。

还使用 G2 的实际 configured glibc 2.44 内部头、preview 交叉 GCC 16.2.0 和
独立合并 overlay 编译本组 15 个目标对象，全部通过 `-Werror`。
最初 `pthread_create` 因上游 `__ASSUME_CLOSE_RANGE` 未定义触发 `-Wundef`，
G2 补充该宏为 0 后再次编译通过。
诊断产物保存在各自 `build/g3_target_objects/`，完整组合构建仍需重跑。

公共线程探针使用真实候选公共头和 `-fno-builtin` 编译，15 个真实目标对象
显式链接到 G2 增量候选 libc.a。修正 getpagesize 后诊断 ELF 的 SHA-256 为
`7688aca4162dd2452f4bb7a0aac55ee573c96f0af36f730293018502425ecacd`。
ELF 检查通过，具有三个 LOAD 和一个 TLS 段，没有动态解释器。
链接显示上游 `__getcwd`、`raise` 未实现的 warning，保持其真实失败。

四组公开接口探针已在包含 sys35 主线程 TP 扩展的真实系统客体中通过：

| 客体 | 结果 | 进程退出 |
|---|---|---|
| TLS/errno、同步、once、TSD、64 位 join、线程配额、双时钟期限 | 全部检查通过 | 0 |
| 主线程 pthread_exit、工作线程 join 主线程、最后线程 atexit | 两个 TSD 析构且 atexit 标记通过 | 0 |
| detached 属性创建与创建后 detach | 交替 16 轮，槽/结果/内核栈页逐轮恢复 | 0 |
| 工作线程持有 stdout 锁时进程 exit | 原生诊断，无死锁，受控终止 | 127 |

上述四次诊断的进程结束后资源均从 `(129720, 3, 1)` 精确恢复到同值。
证据位于私有构建目录 `build/g3_guest_3/report.json`、
`build/g3_last_thread_exit_guest/report.json`、`build/g3_detached_threads_guest/report.json`
与 `build/g3_blocked_stdio_exit_guest/report.json`，各自保留完整串口日志。
新增的两层 cleanup LIFO 检查也已在真实客体通过，exit 0，资源保持相同基线；
诊断 ELF SHA-256 为 `0ec98694658b1a8f47b56779dd1e8f49e4925e456c22b576723317dd156def13`，
记录为 `build/g3_cleanup_guest/report.json`。
这些增量链接用于定位问题；完整源码快照的正式重复验收单独记录。

第一次独立完整 SDK 构建还发现 generic open/open64 的固定参数定义与已安装
可变参数声明冲突。G2 已在 `68fb020` 增加 0023 补丁；正式验收从该修复后的
独立源码重新开始，不沿用失败构建的对象。

完整重建随后通过 `make lib`，但安装阶段复现了构建器竞态：同一次
`make -j4 install-headers install-lib` 同时递归进入相同子目录，覆盖临时依赖
文件和版本文件，最终 `Versions.mk` 含 NUL 而解析失败。G2 在 `eb714bd` 改为
顺序运行这两个安装目标，正式候选已重新从新目录构建。失败安装日志位于
`build/g3_threads_final_sdk/install-sdk.log`，SHA-256 为
`a37b3ed786262a46a3166be901452ec963cfb632d55ba21d19d8b0c873853076`。

## 最终独立 G3-T 完整构建与客体验收

最终代码快照为 `22bd6e2194c6ae86491bfe21b48c77f9f07edfb4`；后续提交只补本工作记录和接口说明。
最终 SDK 使用 G2 的 `0b28799` 生成头依赖修复，全部库/CRT/安装从新目录构建。
构建器结果为 `static_sdk_built`。客体探针直接链接该完整 libc.a，
不再使用诊断阶段的显式对象 overlay。最终系统构建 ID：
`da0f7d1f94b81233`。QEMU 版本为 11.1.3，单核 TCG、
`pc-i440fx-10.0`、512 MiB，通过 xsh 的 `exec-file` 启动。

在 preview SDK 环境执行：

```sh
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output build/g3_threads_release_sdk --jobs 4
python3 scripts/build.py --output-dir build/g3_threads_release_system
python3 tests/glibc_static_guest.py --system-build build/g3_threads_release_system --glibc-build build/g3_threads_release_sdk --suite threads --repetitions 3 --output build/g3_threads_release_threads
python3 tests/glibc_static_guest.py --system-build build/g3_threads_release_system --glibc-build build/g3_threads_release_sdk --suite g2 --repetitions 3 --output build/g3_threads_release_g2
```

`GLIBC_ARCHIVE` 指向上述散列锁定的 glibc 2.44 归档。两次客体 runner 均报告
`passed_subset`，启动前后核对完整 SDK 产物和当前系统源码/产物快照。

| 验收项 | 重复结果 | 实际退出状态 |
|---|---|---|
| 公开 pthread/TLS/errno、600 次锁与读写锁计数、once、semaphore、barrier、TSD、64 位 join、cleanup LIFO、双时钟期限 | 3/3 通过 | 0 |
| 主线程 pthread_exit、工作线程 join 主线程、最后工作线程 atexit | 3/3 通过 | 0 |
| detached 属性创建/创建后 detach，逐轮槽与内核栈回收 | 3/3 通过，共 48 轮 | 0 |
| 活跃工作线程持有 stdout 锁时的受控终止 | 3/3 通过，无死锁 | 127 |
| G2 main 返回与静态 TLS、malloc、stdio、构造/析构/atexit | 3/3 通过 | 37 |
| G2 显式 exit 路径 | 3/3 通过 | 39 |
| 当前系统 newlib malloc/printf/exit 对照 | 通过 | 7 |

线程组 12/12、G2 组 6/6 通过；每个进程退出后的资源均精确恢复到
`(129720, 3, 1)`，对应 stats 的 `free`、`tasks`、`completions`。
该 newlib 对照覆盖单进程基础路径；旧线程版 SDK 的完整同场景矩阵另行执行。

### 最终产物与证据 SHA-256

| 记录/产物 | SHA-256 |
|---|---|
| SDK `build/g3_threads_release_sdk/manifest.json` | `839b9b953be2112610e40afff9acacff5af483c024d594a1e091c18369fa44f9` |
| SDK `usr/lib/libc.a` | `07bd2ad455a33b76e6c12998dbf9e7863069325917fa982b4c441f9a005ad23a` |
| SDK `usr/lib/libm.a` | `d296597e2de25f85b8dfb3496995979ead4d5eafbf860354638dceab6a929b3d` |
| 系统 `build/g3_threads_release_system/manifest.json` | `b8fc8ff7a96f61eb347ef5ec781f9ae78d0da5abe371b2913ec497353b91ab87` |
| 系统 `xos-install.iso` | `8b6df452886b559b92003617aec31fb7ea7d7a9087c38e0430c796825b39c80d` |
| 线程 `build/g3_threads_release_threads/report.json` | `249bce76925d3509945fc780bf21ccde058d2d56d5227055adfcefcd8cdf9d75` |
| 线程 `build/g3_threads_release_threads/serial.log` | `ec8c9b293733e4aba1985c10c6f8a73041bd8239c070e32b1f5850bfda41865f` |
| G2 `build/g3_threads_release_g2/report.json` | `b062b18b8c654ffb22c41a5e9fea78e9767a107c79d51c4eac4064ab40df3d4a` |
| G2 `build/g3_threads_release_g2/serial.log` | `37d5980f0aa5aaefa978862142a3a2d5ac05b418e5ad3056831bc2a526820941` |

公开 runner 的 SHA-256 为
`c60be7006d28cf866441aeff1387d5d3809eab5de251827dffaae974a81a6102`。
完整汇总保留在 `build/g3_threads_release_summary.json`。各报告同时记录每个
实际 ELF 的散列、构建命令、退出输出和每轮资源值。

提交前执行 `git diff --check`，并对相对 G2 `0b28799` 的暂存差异运行公开路径门禁：
33/33 文件为 `PUBLIC_READY`，无发现项。文档收尾后再次核对当前源码与两个构建
manifest 的输入快照保持一致。

## 能力边界与未验范围

当前已实现范围为 x86-64 静态 glibc、原生每进程四线程、私有同步和本页列明的
公开接口路径。取消投递/异步取消、shared/robust/PI 等请求在入口明确失败；
活跃工作线程下正常 exit 的回调和 flush 仍待实现，本轮验证的是可靠的 127 终止。
定时/非阻塞 join 继续返回 `ENOTSUP`。动态 TLS、共享 libc、resolver/DNS、SMP、
完整信号/实时调度及多线程 fork 属于后续工作范围。

以下保持 NOT_RUN，PR 应带上这些缺口供后续成员补充：

- C++ `thread_local` 析构及 glibc 专属 libstdc++ profile。
- dash 入口；本轮运行入口为 xsh。
- 旧线程版 newlib SDK 的完整同场景对照。
- 线程名并发修改、真实时钟故障、退出/分配/调度竞争的完整故障注入矩阵。
- LSan；宿主 ASan/UBSan 已运行，LSan 受执行环境限制未运行。

后续扩大范围时，应从完整 SDK 和当前镜像重建对应探针，并在 PR 记录实际退出、
资源恢复与源码/产物散列。本模块的线程结果独立于 G3-F 文件后端的资格。
