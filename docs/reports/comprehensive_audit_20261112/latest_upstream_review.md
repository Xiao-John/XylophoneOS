本附件为相对 e624 的完整增量审阅和真实复现记录；宿主绝对路径已规范化。结构化结果见 `latest_upstream_results.json`，永久回归在 `tests/ipc_v1_query_compat_test.py`。

# 最新 main 的 IPC IP5 增量审查与 K03 修复

日期：2026-11-12。增量：`e6246faf8eefac305a99528f727b1592ee93a5b2` → `4c9b6f8feb0667d7169167e406da662be789876c`（上游 PR #114）。最终检查对象是根代理合并该增量后、保留本轮 K01 等修复并追加下述 K03 的工作树。本增量审查未改变上游已经开放的 supported manifest；提交状态见总报告。

## 结论

发现并经授权修复一项确定的 ABI 兼容性错误 **K03**。另发现 K01 宿主抽取器缺少新依赖，已交根代理修正。IPC fastpath 的调度选择、端点索引和 payload 复制增量经完整 diff 及相关调用/回收上下文核对，未发现其他可以确认的新增运行时错误。此结论不替代客体调度、deadline、硬件、性能或资源资格。

上游本次已经开放 IP2/IP3 的四个能力，必须更新此前“仍全部 unsupported”的审计口径：runtime supported mask 是 **0x0f**，普通和线程 SDK manifest 是 **supported**，列出 `endpoint_call_v1`、`deadline_v1`、`notification_v1`、`wait_set_v1`；`bulk_grant_v1` 的 0x10 仍关闭。上游契约引用 PR #111 的同一构建三轮历史客体验收作为开放依据。这不是本轮重新运行的证据。IP5 最新代码自身的完整构建、客体功能/性能探针仍为 **NOT_RUN**，其工作日志也明确没有性能数值。

## K03：默认 feature query 破坏旧 SDK 的保留字段约束

### 确定触发与影响

旧 `ipc_v1_feature_query` 固定为 version 1、72 字节，offset 56 和 64 是两个必须为零的保留字。e624 中真实 SDK `query_features()` 会检查这两个字，任何非零值都返回 `ipc_v1_error::state`（-112）并清空输出。

IP5 在保持 version 和 size 不变的情况下把 offset 56 改为 `direct_switch_count`，默认查询无条件回传全局累计值。只要任一进程成功触发一次满足条件的短消息直切，此后旧 SDK 查询就稳定报 -112。它不是需要稀有硬件状态的假设竞态；计数变成非零后，所有这种旧查询都会触发。新 SDK 的原 IP5 wrapper 已去掉该字的零检查，因而仅运行新 SDK 探针不能发现旧应用回归。

复现直接使用公开同仓历史的旧 ABI/SDK 头和实际新内核查询分支；未重写查询业务逻辑。只以宿主接口替代 syscall 运输、页合法性和计数初值，旧/新类型放入独立编译单元、内核类型另用命名空间隔离。实际结果：

| 内核累计值 | 旧 SDK + 未修 IP5 查询 | IP5 原新 SDK + 未修查询 |
|---|---|---|
| 0 | rc=0，supported=15 | rc=0，supported=15 |
| 1 | rc=-112，输出清零 | rc=0，supported=15 |

原始复现的源码、编译命令、版本和输出在 `latest_ipc_validation/abi_compat_results.json` 及同目录文件。这是宿主 ABI 复现，没有执行 guest 直切。

### 已实施的最小兼容处理

- ABI 增加仅 query action 使用的 `ipc_v1_query_flag_direct_switch_count=0x1`，通过既有 syscall arg3 显式选择计数。version、72 字节大小和字段偏移不变。
- 默认 arg3=0 时 `direct_switch_count` 输出 0，旧调用者看到的两个保留字仍为 0；显式设置该位才返回真实累计值。其它 action 仍不允许非零 arg3，未知位继续返回 invalid_argument。
- SDK `query_features(output, bool include_direct_switch_count=false)` 默认使用旧请求；IP5 probe 的 baseline/observed 两处显式传 true，统计没有删除。普通 feature 查询继续默认调用。
- 当前新 SDK 的默认查询仍可以发送给旧内核；对旧内核显式索取计数会收到 invalid_argument，不伪造或自动降级计数结果。
- IPC 契约和 E04 接口说明同步该规则；顺便纠正契约残留“当前 SDK supported set 为空”的过期段落。runtime/manifest 的 0x0f 支持状态没有回退。

行为修改共 4 个文件 **+12/-6**：`src/kernel/arch/x86_64/tasks.cpp`（+5/-2）、`src/shared/include/xos/ipc_v1_abi.hpp`（+2）、`src/user/include/xos/ipc_v1.hpp`（+3/-2）、`tests/fixtures/ipc_v1_fastpath/ipc_v1_fastpath_probe.cpp`（+2/-2）。另有契约/E04 两份文档 +18/-8 和一份永久宿主回归。没有新增通用防御层、锁、ABI 版本或私有 syscall。

### 永久回归

`tests/ipc_v1_query_compat_test.py` 固定读取公开同仓提交 `e6246faf8eefac305a99528f727b1592ee93a5b2` 的真实旧头，对照工作树真实新头；实际内核 query 前置 flags 检查、query 分支、copy/header helper 均从源码原样抽取。`--source` 可指向旧 IP5 文件，便于同一测试重放修复前失败。

9 个场景为：旧 SDK 在累计 0/1 时默认查询两项；新 SDK 在累计 0/1 时默认/显式查询四项；未知 flags 0x2/0x3 两项；非 query action 使用计数 flag 一项。旧版测试在旧 SDK 查询断言稳定失败；修后输出 `IPC_V1_QUERY_COMPAT_CASES_PASSED=9`。前后命令、退出码和原始输出保存在 `latest_ipc_validation/k03_before_after.json`。

## K01 与最新调度/复制的兼容性

K01 的 `sys_process_wait` 仍先检查已唤醒 waiter 的完成记录所有权，再进入 ready 消费分支；轮询未就绪语义保留。IP5 没有更改这段逻辑。新 `schedule(frame, preferred)` 在选定目标后仍通过原来的地址空间/FPU 切换及 `deliver_wait`，没有旁路 process completion 的复制和 pin 清理。

本轮先实际运行旧 K01 抽取脚本，因新 `deliver_wait` 调用 `copy_ipc_payload` 而缺少抽取定义，编译失败两处。已经交根代理修正为“实际源码含该函数时原样抽取”，根代理确认新树回归通过，并保留 `--source` 旧源码兼容。该测试整合修正由根代理拥有；本代理没有重复修改 K01 测试。

## 其余增量核对

| 范围 | 核对结果与实际边界 |
|---|---|
| preferred receiver 直切 | 仅非 poll、请求与回复容量均不超过 64 字节、已经通过共同权限/地址/pin/入队与交付路径的调用可提供 preferred。调度器再次要求 ready、进程活跃及 continuation owner 合法，否则回退原 picker；共享完成交付路径仍执行。没有把这次源码核对称作真实 deadline/抢占资格。 |
| endpoint handle 索引 | 512 槽开地址索引承载既有最多 256 个 endpoint handle 记录。插入失败回滚记录且不推进下一 handle；查找仍检查 used/value/holder_pid；endpoint close 与进程撤销均通过统一删除清除索引；墓碑不提前截断碰撞探查。全量检索未见遗漏的 endpoint handle 重置路径。未新增无依据的额外校验。 |
| payload word copy | 入口原有 user_range_ok、长度上限、输出 pin 和快照/不重叠关系保留。旧 copy_from_user/copy_to_user 本身也只是 raw copy 包装，不含被新函数跳过的隐式权限逻辑。复制按完整 u64 和尾字节处理，使用 unaligned-safe builtin memcpy，未发现长度/页界新越界；真实页表/TLB 行为尚未运行。 |
| feature mask 与 manifest | ABI supported mask=IP2\|IP3=0x0f，与共享 Python manifest 四项一致；bulk_grant 保持关闭。参考模型不是后端资格，合并后本轮实际运行 19 项通过。 |
| IP5 测量范围 | probe 是同进程线程的 blocked receiver 与 polling server 两种策略比较，不是强制同一请求切换 slow/fast path；计数是全局累计。工作日志和 runner 已限制 QEMU 数值解释。没有声称延迟改善或当前修订已通过资源基线。 |

## 本轮验证及未运行项

| 验证 | 结果 |
|---|---|
| 固定旧 SDK + 实际 IP5 query 的初始复现 | 旧 SDK 在 count=1 时稳定 -112，证实 K03 |
| 永久 K03 回归对未修 IP5 / 当前修复源码 | 前者失败；后者 9 场景通过 |
| 合并后 IPC 参考模型 | 19 项通过；这是模型 |
| IP5 probe 严格宿主语法检查 | PASS，`-std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow` |
| 新 Python 测试语法、改动 whitespace 检查 | PASS |
| 最新 tasks.cpp 默认、VM1、VM1+COW1 | 三个严格独立宿主对象全部 PASS，使用实际仓库 COMMON_FLAGS + X86_FLAGS |
| 完整目标构建、链接、BIOS、真实调度/TLB/FPU、IPC guest、IP5 延迟与当前资源资格 | **NOT_RUN** |

当次编译器明确记录为 `/usr/bin/x86_64-linux-gnu-g++-14`，`g++ (Debian 14.2.0-19) 14.2.0`。完整三个编译命令、版本输出、源哈希及退出码在 `latest_upstream_results.json` 的 `latest_tasks_compile.json` 字段。生成的 `user_blobs.hpp`、`user_images.hpp` 仅使用声明替身，未伪造实际映像字节或构建 ID；没有链接。此前 kernel 报告的 22+3 个对象是 e624 阶段证据，本增量仅重新编译最新 tasks.cpp 的三个配置，不能把原批次改称全部在 4c9 后重跑。

本次新增阅读方式已合入 `repository_inventory.csv`；其中任务大文件标记为“完整增量 diff + 指定上下文”，不冒记为 5,500 行再次逐字通读。两份 ABI/SDK 头、manifest、IP5 新 fixture/runner/工作日志、最新 IPC 计划与本轮新测试已全文阅读。原先全仓阅读清单仍保留。


---

# 最新上游 IPC 测试增量审查

以下为 K03 修复前完成的测试范围只读子审查记录；该子审查未额外修改源码。最终 K03 改动、probe 两处显式取数和最新编译验证以上半部为准。

审查基线：`e6246faf8eefac305a99528f727b1592ee93a5b2`。新上游：`4c9b6f8feb0667d7169167e406da662be789876c`，对应本轮收尾时新合入的 IPC fastpath 变更。先通过 `git show upstream/main:...` 读取上游文件；根代理通知合并完成后，再核对当前模型 M01 差异并运行宿主检查。此测试子审查没有额外修改源码、测试、主报告或冻结证据。

## 阅读范围

独立清单：`latest_ipc_test_reads.txt`，4 个路径。阅读方式应保留区别，不能把以下所有项都计为本轮首次全文阅读：

| 路径 | 本轮阅读 |
| --- | --- |
| `tests/fixtures/ipc_v1_fastpath/ipc_v1_fastpath_probe.cpp` | 上游新增文件全文，201 行、8,667 字节 |
| `tests/ipc_v1_fastpath_guest.py` | 上游新增文件全文，152 行、7,777 字节 |
| `tests/ipc_v1_guest.py` | `e6246fa..4c9b6f8` 完整差异；只有开头范围说明变化，没有执行流程变化 |
| `tests/ipc_v1_reference_model.py` | 上游全文 563 行；另读 `e6246fa..4c9b6f8` 完整差异及 `upstream/main` 到当前工作树的完整 M01 差异 |

为核对快路径与 badge 的实际来源，另外阅读了 `src/kernel/arch/x86_64/tasks.cpp` 的 call 入队、direct_receiver 选择以及 queued receive 片段；这是定向片段复核，不计为新增整文件全读。

## M01 兼容结论

**M01 caller-first badge 修复与最新上游兼容，合并后参考模型 19/19 通过。**

上游对模型的变化是把 `supported` 期望更新到 `0x0f`，并把 SDK manifest 期望更新为 endpoint、deadline、notification、wait_set 四项已支持特性。它没有修正旧的 caller-first badge 传递：上游原版仍从接收方 capability 取 badge。

当前审计修改仍完整保留：`call_record` 增加 `badge`，`submit_call` 保存调用方 capability 的 badge，caller-first 的 `begin_receive` 使用 `call.badge`；新增 `test_call_first_preserves_caller_badge` 断言返回 `0xabc`。现有 receive-first 用例也通过。该修改仍然只是模型修复；没有因本轮审查改动内核 IPC 或支持声明。

定向阅读当前内核确认 call 入队已经保存 `handle->badge`，queued receive 返回 `call.badge`。新 direct_receiver 选择位于入队/投递之后，不改变这两个 badge 来源。本次没有执行客体调用来证明内核路径的运行表现。

## 新增快路径测试实际覆盖

- probe 使用同进程的线程和 endpoint，覆盖 blocked receiver / polling fallback 两种服务策略、0/8/64/128/256 字节，共 10 种组合。每种先运行 1 轮预热，再保留 120 个测量样本。
- 核对请求序号、label、请求字节、reply label / length / payload，以及 `reply_receive` 的 `reply_consumed_out`。结尾检查 thread join、server 结果和 endpoint close。
- blocked receiver 的 0/8/64 字节用例要求 direct switch 计数增量大于 0；其余组合要求为 0。call 的 request length 和 reply capacity 与当前内核 `<= 64` 的选择条件一致。polling fallback 是另一种接收策略，不是强制同一 workload 走内核 slowpath 的开关。
- guest runner 还要求完整 PASS 标记、退出码 0、10 条分布输出、前后资源计数一致。报告和说明都把 QEMU 时延限定为观察数据，没有硬件性能承诺。

没有在这两个新文件中确认需要本轮立即修改的执行缺陷。

## 需要保留的资格边界

1. **新 fastpath probe 不替代 M01 badge 回归。** 它使用同进程创建的 endpoint，默认 badge 为 0，没有委派非零 badge，也没有检查 receive 的 `badge_out`。本轮 M01 的 `0xabc` 结论来自独立参考模型用例。

2. **runner 尚未自动证明 SDK、系统镜像和当前源码同源。** 它核对镜像与系统 manifest 的 SHA-256，以及 SDK artifact 与其各自 manifest 的 SHA-256，但没有交叉比较二者的源码/工具链绑定。probe 编译又优先使用当前仓库的 user/shared 头文件。因此帮助文字中“使用同一源码/工具链构建的系统和 threading SDK”仍是调用者必须满足的前置条件，不能把各自哈希自洽说成已经自动证明同源。这是直接可见的验收边界，本轮只记录，不扩大改动。

3. 本次没有合适的交叉工具链、threading SDK、构建镜像和 QEMU 环境，未链接 probe、未启动 guest、未采样时延、未观测真实 direct switch 次数、未执行客体资源基线或 syscall 验收。宿主模型通过及 C++ 语法通过不等于这份新的 guest 测试通过。

## 已执行检查

均在合并最新上游后的仓库根执行，全部退出 0：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/ipc_v1_reference_model.py
c++ -std=c++20 -Wall -Wextra -Werror -fsyntax-only -DXOS_THREADED_RUNTIME -I src/user/include -I src/shared/include tests/fixtures/ipc_v1_fastpath/ipc_v1_fastpath_probe.cpp
PYTHONPYCACHEPREFIX="$PWD/../ui_audit/pycache" python3 -m py_compile tests/ipc_v1_fastpath_guest.py tests/ipc_v1_guest.py tests/ipc_v1_reference_model.py
```

结果：参考模型 **19 tests / OK**，包含 caller-first 与 receive-first badge；新增 fixture 宿主 C++ 语法检查通过；3 份 Python 文件语法检查通过。C++ 命令只做语法核验，没有链接 XOS 运行库，没有执行 fixture。

原始命令输出经路径规范化后收入 `latest_upstream_results.json` 的 `upstream_test_validation` 字段。此测试子审查没有产生额外源码修改；随后 K03 的变更与验证已在上半部单列。
