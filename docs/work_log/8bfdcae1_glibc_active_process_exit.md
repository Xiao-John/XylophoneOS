# glibc 活跃工作线程下的正常进程退出

## 范围与依赖

本模块基于 PR #153 的 `07695514b01f004e53bd4355fae93b1d4f3b15a5`，组合
PR #154 的 glibc 2.44 来源签名核验。G1/G2/G3 的 TLS、线程与文件运行库继续复用；
默认 newlib SDK 保留。交付边界是正常进程退出、同一生命周期机制的超时/故障路径
及对应 glibc/原生 ABI 回归。参考[线程契约](../contracts/threading.md)、
[glibc 静态线程契约](../contracts/glibc_static_threads.md)、
[来源核验记录](53bc719e_glibc_source_authentication.md)。

原 G2 在发现多个活跃线程时直接退出 127，因为旧 sys51 会先停止并回收其他线程，
随后运行 atexit/stdio 可能等待已经失去所有者的锁。现在先领取唯一清理责任，
保留现存线程的调度与 I/O，待调用者 TLS 析构、atexit/fini 和 flush 完成后再由
sys_exit 统一结束进程。相关文件为 `tasks.cpp` 的线程生命周期路径、公共
`thread_abi.hpp`、`thread_core.hpp`、glibc 私有 `xos_process_exit` 桥、0021 补丁
与三份 G3 夹具。新增代码使用 Apache-2.0，上游文件保留原许可证。

## 接口与实现选择

- sys51 增加显式 mode 1；mode 0 的旧参数布局和停止 peers 行为保留。
  新请求为 32 字节、version 1，含绝对单调 deadline、非零超时退出状态和严格
  为零的保留字段。deadline 必须在未来、最多 30 秒且有限。
- 清理窗口使用独立 deadline 状态，复用现有 `exit_owner`。通用 `closing`
  会拒绝 IPC/VM，因此在窗口内保持清理所需功能可用。thread profile、prepare/start
  和本进程 exec/fork 入口关闭；预留线程仍可 abort，现存线程仍可正常清理、join。
- 同一所有者重复调用保留首次 deadline 和超时状态。其他线程取得 busy 后使用
  原生 sleep 等待进程终止，不获取 glibc exit 锁。递归 exit 沿用上游递归回调处理。
- deadline 检查位于安全调度入口与 idle/continuation 等待循环，扫描上限 8 个进程。
  它不会在尚需继续执行的不可抢占内核调用中销毁当前地址空间。到期只进入既有
  整进程终止/回收路径；有 VM continuation 时使用既有取消与回滚机制。
- glibc 选择 30 秒窗口、超时状态 127。正常 return/exit 保留调用者状态；
  quick_exit 保留其回调和缓冲规则。所有者主动 pthread_exit 以登记失败状态结束，
  fault 保留实际向量，显式 `_exit` 与监督 kill 保持原有整进程语义。
- 最后线程仲裁可转入清理窗口，恢复其收尾所需 I/O。工作线程主动 return 时完成
  TLS、TSD、运行库清理后才进入原生退出握手。仍在执行的其他线程由最终进程退出
  统一回收，应用需要它们的析构时应主动协调并 join。

## 实际验收

使用 release `xos-glibc-sdk-preview` 中的 GCC 16.2.0、Binutils
2.47.20260726、GNU make 4.4.1 和 QEMU 11.1.3，x86-64 TCG、单 CPU、512 MiB。
预览 SDK 的工具用于构建独立 glibc sysroot；正常/服务死亡镜像各自使用私有输出。
所有客体使用新的 FAT32 测试盘和串口通道，QMP 关闭。

正式 `glibc_static_guest.py --suite all --repetitions 3`：**61 项按预期通过**
（20 个场景各三轮，加一个文件服务死亡场景）。报告状态为 `passed_subset`。
当前系统的普通 newlib malloc/printf/exit 控制程序通过。每次普通客体运行后
free pages / tasks / completions 精确恢复为 **129719 / 3 / 1**。

| 场景 | 实际结果 |
|---|---|
| G2 return / exit | 状态 37 / 39；缓冲输出、atexit 与 fini 顺序通过，各三轮 |
| 既有 G3 线程 | TLS/errno、私有同步、时钟等待、最后线程、16 轮 detached 创建与回收通过 |
| 活跃 peers 下 return / exit | 状态 37 / 39；持有 stdout 和应用 mutex 的线程继续执行并释放锁；仍有 malloc 循环与 cond 等待线程时完成退出 |
| 调用者与工作线程析构 | 实际 `__cxa_thread_atexit_impl` ABI 验证两套 TLS 地址/值与顺序；工作线程 TLS 析构先于 TSD；join 保留完整 64 位结果 |
| 正常回调与文件 flush | atexit 逆序、fini 各执行一次；后续独立进程读到 main/callback/fini 的完整文件字节，并成功关闭、删除文件 |
| 并发 / 递归 / worker 发起 exit | 分别保留状态 37 / 43 / 41；回调无重复；全部恢复资源 |
| quick_exit | 状态 45，quick 回调逆序；普通 atexit 与 stdout 缓冲均未执行/刷新 |
| 原生 ABI 负向与所有权 | 错误 mode/version/size/reserved、坏指针、过去/无限/超界 deadline、零超时状态均拒绝；拒绝后仍能创建线程；窗口内 prepare/start 被拒绝且输出保持，已有预留可 abort |
| 首次 deadline 与状态保持 | 同 owner 重入不能将 1 秒窗口改为 30 秒，另一线程不能接管；忙循环最终状态 125；三轮宿主耗时 1.30–1.53 秒 |
| 全部应用线程阻塞 | worker 持有 stdout 并阻塞在 cond，owner 在 flush 阻塞；统一单调 30 秒期限后状态 127，记录 `exit_cleanup_timeout`，未输出未刷新的缓冲内容 |
| owner fault / 主动 pthread_exit | 分别得到 faulted/vector 6 和 exited/127；仍活跃的 peer 一起回收 |
| 既有 G3 文件、跨 libc exec 继承 | 单线程、多线程文件接口与 newlib parent → glibc receiver 全部通过 |
| 文件服务死亡 | 真实测试服务退出、释放 246 页；104 个检查通过；资源精确为 **129965 / 2 / 1** |

30 秒客体期限的三轮宿主耗时为 80.73、32.50、33.03 秒；首轮处于并行构建的
TCG 负载下。期限采用客体统一单调时域，宿主耗时作为环境观测记录。

额外检查：

- 公共 C++ 请求与 glibc C 桥的 size/deadline/status/reserved 偏移编译核对通过。
- 现有 `kernel_process_wait_race_test.py` 的正常/故障退出、孤儿回收、builder
  取消、kill 传播、等待唯一消费和跨页 pin 检查通过。
- gpgv 2.2.40 实际验证来源通过；来源测试的有效签名、篡改 archive/signature/key
  拒绝及既有证据保护 5 项通过。普通宿主未安装 gpgv，完整验证在 preview 工具环境执行。
- 文档/ABI 登记一致性和公开证据路径检查通过。最终平铺证据索引核验见下节。

初次诊断夹具使用了当前 profile 尚未实现的 nanosleep，导致断言状态 95；
夹具改用已有 CLOCK_MONOTONIC cond_clockwait 后进入正式验收。初次报告保留在
`build/active_exit_probe/`，正式结果位于不同目录，源码和产物哈希单独绑定。

## 产物与证据

SDK 的 184 项构建输入、685 项安装产物均在构建和客体验收前后核对；普通与
故障镜像的源码快照一致，测试专用编译标志分别记录。正式系统 build ID 为
`8d7e54a8246d6939`，故障系统为 `f5597fa00baf97a8`。

| 文件 | SHA-256 |
|---|---|
| `build/active_exit_verified_sdk/manifest.json` | `13a625c5b69b554575ea44bd562d6c43d3a5a2fb581c898821cccb846bf5f152` |
| `build/active_exit_verified_sdk/source_verification/report.json` | `01ff50fd9499930126eab8e26d27f7ef53716369ece71d89383efd279a624bd1` |
| `build/active_exit_qualified_system/manifest.json` | `d900bc536a837eb2b06581a08210b009621d7f26f08e7abb5b6643bf0261abac` |
| `build/active_exit_qualified_system/xos-install.iso` | `f56652a21e51f0876ecf36b4fbbc21d52907e585eb7c08d95a2d19cb1e8fff47` |
| `build/active_exit_qualified_death/manifest.json` | `e7d6137a3fc084299168f779925d64f28d53d8c2f4a73272c8ae2661df80bbca` |
| `build/active_exit_qualified_death/xos-install.iso` | `dc6fda6a16ecd37a0d5afdf1868b87339357121200f551549a40d6e679cbb452` |
| `build/active_exit_qualified_guest/report.json` | `e411bf16e818a6b6ac5270b3a422f88ed2edfb88dc496825e069125a01c35855` |
| `build/active_exit_qualified_guest/serial.log` | `ad5f2fb75becf77f1016e28d83648ef71b2acc520a35798dccfac0c43a5334ca` |

`build/active_exit_evidence_index.json` 是平铺文件索引，包含 SDK、系统产物、程序、
构建记录、正式报告与串口日志；提交前执行 `verify_evidence_index.py`，**1401/1401**
匹配。索引 SHA-256 为
`92f03ccbb89060ff68edde7c397b722f60b3109a12d8dc68e728ed7c7651b517`。
本地证据目录为可重建输出，关键结果和产物散列保留在本记录及 PR 中。

## 复现

`XOS_SDK_RUN` 指向已经核对 release 归档的 preview 工具环境入口；
`XOS_GLIBC_ARCHIVE` 指向锁定的 glibc 2.44 归档。以下输出目录必须为新目录。

```sh
"$XOS_SDK_RUN" python3 scripts/build_glibc_sdk.py \
  --archive "$XOS_GLIBC_ARCHIVE" --output build/active_exit_verified_sdk --jobs 4
"$XOS_SDK_RUN" python3 scripts/build.py --output-dir build/active_exit_qualified_system
"$XOS_SDK_RUN" python3 scripts/build.py --glibc-files-death-probe \
  --output-dir build/active_exit_qualified_death
"$XOS_SDK_RUN" python3 tests/glibc_static_guest.py \
  --system-build build/active_exit_qualified_system \
  --glibc-build build/active_exit_verified_sdk \
  --death-system-build build/active_exit_qualified_death \
  --output build/active_exit_qualified_guest --suite all --repetitions 3
"$XOS_SDK_RUN" python3 tests/glibc_source_auth.py \
  --archive "$XOS_GLIBC_ARCHIVE" --output build/active_exit_source_auth_sdk_test
python3 tests/kernel_process_wait_race_test.py
python3 tests/docs_consistency.py --output-dir build/active_exit_docs
python3 tests/check_public_evidence_paths.py --index --base 07695514b01f004e53bd4355fae93b1d4f3b15a5
python3 scripts/verify_evidence_index.py build/active_exit_evidence_index.json
```

只运行退出专项可使用 `--suite exit`。该套件通过实际 libc 公共接口及单列原生 ABI
探针观察状态、顺序、持久内容与回收，完整 all 套件还提供受影响 G2/G3 回归。

## 缺口与下一步

- dash 入口、SMP、真实硬件、长压力和完整 C++/libstdc++ 应用未在本模块验收。
  当前普通 newlib 控制已运行；专门的 newlib 线程 SDK 未重新构建并全量验收。
- 原生 deadline 是单调时域的有界终止机制，应用回调/锁正确性仍由应用负责。
  需要超过 30 秒正常收尾的应用须另行设计其退出策略，不能通过重复 claim 延期。
- 未扩展异步 pthread cancel、全量信号、多线程 fork 或动态 TLS。G4 的真实
  libstdc++ TLS、std::thread、异常与析构验收使用独立 profile 和新证据。
- 网络 exec 通道撤销等其他分支的内核改动在组合后需重新绑定系统镜像并执行
  受影响回归；本记录对应上述冻结源和产物。
