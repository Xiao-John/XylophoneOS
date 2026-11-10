# 0223 Season-4 报告修复：Interactium 窗口/输入、音频服务/SDK、speaker 租约

输入为桌面 `归档_副本.zip`（sha256 `a760b0f6…dc57`）内 6 份 `found_bug_s4*.md`，
其中 `(3)` 与 `(4)` 字节级相同（sha256 `a277852f…a059`），去重后 **5 份唯一报告**。
报告基线 `c82bd8aa`（= origin/main，PR #94 已以 `5562d8ab` 合入，其上为 #91–#97 的
VM/Interactium/音频/文档线）。在独立 worktree `.wt-s4`（分支
`codex/bug_hunting_s4_fixes`）上按文件互斥并行处理，每条先独立验证再修。

## 去重映射与结论（11 个独立问题：10 修 + 1 虚报）

| # | 问题（报告来源） | 结论 |
|---|---|---|
| W1 | 窗口配额是全体会话共享 8 槽，违反契约"每会话 8 窗"（(1)） | CONFIRMED 已修 |
| W2 | 输入队列满时静默丢最旧事件，不置 lost 不合成 resync（(1)(3)） | CONFIRMED 已修 |
| W3 | 跨窗口指针旧窗口收不到离开事件（(1)） | CONFIRMED 已修 |
| W4 | 焦点窗口销毁/隐藏/断连后键盘事件丢失，且 `find(0)` 误配空槽（(1)，含自纠） | CONFIRMED 已修 |
| W5 | 焦点切换后按键释放错投新窗口，旧窗口 held 卡死（(1)(5)，宿主实测复现） | CONFIRMED 已修 |
| T1 | Interactium 会话关闭只关 send，receive 端点泄漏（s4） | **REFUTED 虚报**（见下） |
| K1 | 2000 ms 合法音符 vs 2 s PIO 租约必撞，最长音符判 expired（(1)(2)(5) 三条重复） | CONFIRMED 已修 |
| A1 | 音频服务把成功发送（返回 0）误判为失败（判 ==48）并立即断开、撤销未读回复（(1)(5)） | CONFIRMED 已修 |
| A2 | `audio_tone parse_number` 把非法/溢出频率当 0 静默休止符成功退出（(2)） | CONFIRMED 已修 |
| C1 | 音频 SDK 全部请求 `version=0 size=0`，服务端门槛必拒（(1)(3)(5) 三条重复） | CONFIRMED 已修 |
| C2 | 音频客户端对命名端点用 sys81 wait（要求 `generic_channel`）被 denied，握手前即失败（(1)(5)） | CONFIRMED 已修 |

### T1 虚报详情（未改任何代码）

报告称 `ipc_session_transport::close()` 只关 `channel_.send` 导致 receive 端点永久泄漏。
反驳（源码逐环核对 + 逻辑抽取模型实测）：`sdk::ipc_channel_close` → `sys_ipc_endpoint`
close → `revoke_ipc_channel(endpoint->channel_id)`，而同一 `ipc_channel` 的 send/receive
两条 `endpoint_record` **共享同一 `channel_id`**（tasks.cpp 两处均写 `request`），
`revoke_ipc_channel` 释放该 channel_id 下**整对**端点——显式 close 一次即全部释放。
报告的"内核仅在进程退出时回收（release_channels）"也错：`release_channels` 只管
`generic_channel`，`generic`（ipc）端点由 `destroy_task` 中 `if (endpoint.generic)`
一段兜底；`bind()` 覆盖泄漏、`interactium_client.cpp:64` 配对失衡两条同理不成立。
混淆根源是把 `sdk::channel_close`（单端点，`channel_action::close`）与
`sdk::ipc_channel_close`（整对，`ipc_endpoint_action::close`）当成同一个；audio 侧
"成对关闭"是冗余但无害的防御写法，不能反推单关一条会泄漏。
证据：临时目录中的逻辑抽取模型程序（从 tasks.cpp 抽取真实路径编译）输出
`after close: service send=0 receive=0 | client send=0 receive=0`。
另注：报告 (1) 对 W4 的"queue_input 返回 false"初判有误并已在报告内自纠（实为
返回 true 且事件排入 ID 0 队列）——底层 bug 属实，不计虚报。

## 代码修复

- **W 组**（`window_manager.{hpp,cpp}`、`service.{hpp,cpp}`、`tests/interactium_model_test.cpp`、
  `docs/contracts/interactium.md`）：
  - W1：窗口表容量 = `max_sessions(4) × max_windows_per_session(8)` = 32，`create` 按
    owner 即时扫描计数，≥8 拒绝；契约 First-Version Limits 补记 guest 像素池
    `surface_capacity=8` 的独立渲染预算（既有内存限制，未改）。
  - W2：每窗口 `pending_lost_` 饱和累计驱逐丢失；仅在有空位时投递现有
    `input_kind::resync`（携带 lost 与最近指针/按键状态）；每窗口 `next_sequence_`
    保证合成与真实事件严格递增（QPA 对非递增 sequence 会 qFatal）。
  - W3：跟踪 `pointer_target_`，跨窗口/移出时把当前指针事件复制投给旧窗口（坐标
    仍在旧窗口内则平移到边界外 1 px），destroy/hide/disconnect 三路径清理。
  - W4：新增 `refocus_top()` 按 z 序在剩余可见窗口重选焦点，destroy/set_visible(false)/
    destroy_owner 三路径调用；`find/find_mut` 对无效 id（含 0）不再匹配空槽。
  - W5：`pressed_` 表按 code 记按下窗口，释放优先回投按下窗口（已销毁则丢弃），
    不再按当时焦点路由；模型用例覆盖焦点切换/销毁路径。
  - `qxos.cpp` 与 `interactium_abi.hpp` **未动**（纯服务端方案达成，无 ABI 新增）。
- **K1**（`src/kernel/arch/x86_64/tasks.cpp`，仅 5 行）：`pc_speaker_lease_ns` 改为
  `max_note_ms(2000) + 500 ms = 2_500_000_000`，`#include <xos/audio_abi.hpp>` 与
  `max_note_ms` 同源（协议上限调整自动跟随）；核对无任何测试断言旧值 `2000000000`。
- **A1**（`src/user/programs/audio_service.cpp`）：`send_response` 成功判定改为
  `== 0`（内核 `ipc_send` 成功返回 0）；`ipc_error_full` 属瞬态——有界等待
  （40 ms = 4 tick，`sys_ipc_wait(try_send)` + `sys_sleep_until` 轮询）后重试一次，
  硬错误才断开；`close` 与 overflow busy 路径改为 `respond()` 成功后
  `wait_reply_consumed()` 再关闭，不再撤销未读回复。
- **A2**（`src/user/programs/audio_tone.cpp`）：`parse_number` 返回 `bool`，非法/溢出
  `return 2`（与既有参数错误码一致），合法 0 仍为休止符。
- **C1/C2**（`src/user/include/xos/audio_client.hpp`）：`exchange` 统一填
  `version/size/reserved`（一处覆盖 5 个操作）；新增基于 sys85 `ipc_wait(try_send/
  try_receive)` + 有界休眠的端点等待（与命名端点语义匹配），保留 1 s 绝对截止与断线
  传播；`channel_io.hpp` **未改**（grep 全部调用方均为 `channel_open` 得到的
  `generic_channel` 端点，sys81 对其本就正确）。
- **事实登记同步**（租约 2 s → 2.5 s 后过期的陈述）：`docs/contracts/pio_grant.md`
  两处、`docs/contracts/audio_service.md` 一处、`docs/e04_loader_sdk.md` 两处、
  `docs/plans/audio_output.md` 两处；音符 10–2,000 ms 范围**未变**未动；历史 work_log
  不改写。

## 证据（2026-11-09，worktree `.wt-s4`，build `8766d46d56502ad2`，kernel 671840 字节）

宿主（g++，项目严格标志另测）：

```text
tests/interactium_model_test.cpp     exit 0（新增 W1/W2/W3/W4/W5 共 11 组用例）
tests/interactium_transport_test.cpp exit 0
tests/audio_service_reply_test.cpp   22 asserts ok（修复前同源 10 项 FAIL 实测复现）
tests/audio_tone_args_test.cpp       10 cases + play 计数 ok（修复前 4 项 FAIL）
tests/audio_client_host_test.cpp     passed（header/sys85 回归守卫、满队列重试、1 s 截止、断线）
python3 tests/pc_speaker_lease_check.py  PASS lease=2500000000（旧值 static_assert 负控 FAIL）
g++ ASan+UBSan 模型/传输测试          exit 0 无告警
```

客体（QEMU）：

```text
python3 tests/interactium_guest.py   passed（截图 build/interactium_demo.png，
                                     覆盖内核改动后真实启动 + 双窗口显示）
```

基线对照构建（stash 掉内核 5 行后）：build `7f21460883364dc6`，kernel 671840、
`legacy_images_available=false`——与含修复的构建同尺寸，证明下述基线问题与本组无关。

## 失败 / 未运行 / 基线既有问题

- **`make smoke` 家族基线已断（本组发现，非本组引入，未修）**：`c82bd8aa` 上 kernel.bin
  = 671840 > 512 KiB（`fdadfe77` 时为 512080，恰在门槛内；#91/#93/#95 VM 与 #96 音频
  的内核改动越线），`scripts/build.py` 按设计不再产出 `xos.img`
  （`legacy_images_available=false`），**20+ 个引用 `artifacts['xos.img']` 的客体
  smoke**（含 `make smoke` 的 `file_smoke.py`）在基线即 `KeyError: 'xos.img'`。
  已实测基线（stash 对照）确认。修复需三选一：把这批测试迁到 ISO、恢复小内核 legacy
  产物、或拆内核——属 VM/音频线与测试基建的裁决，超出 S4 报告范围，留待裁决。
- **`tests/interactium_aurora_guest.py` 未运行**：需要工作盘上的 `/AURORA_DESKTOP.ELF`，
  而该产物的构建入口不在 `scripts/`/`Makefile`（grep 无引用），且 `build_aurora.py`
  需要绑定 0.0.2-1103 身份的 SDK 发行树与 Qt 静态构建树（本 worktree `.cache` 为空）。
  PIL 依赖已用临时隔离 venv（Pillow 13.0.0）备好；缺的是 ELF 与 Qt/SDK 资产。
- **音频端到端未跑客体**：`tone 440 2000` → completed 的前后对比无现成客体套件
  （音频线无 guest 测试）；K1/A1/C1/C2 的客体端到端（真实命名 IPC 握手→提交→状态→
  关闭）仅有宿主模型覆盖。
- **A1 已知限制**：对端 40 ms 内始终不读回复时服务仍超时关闭并撤销该回复（刻意的
  有界取舍，证据 `stuck peer: polls=5 wait_ns=40000000`）。
- **K1 已知限制**：强制静音上界由 ~2 s 放宽到 2.5 s + 1 tick；启动+调度延迟 ≥500 ms
  的极端情况下最大音符仍会过期（测试输出已标注边界）；owner 退出/被杀路径仍立即静音。
- **W1 残留**：guest 像素池 `surface_capacity=8` 仍限制"可绘制窗口"总数为 8（既有
  内存预算，契约已记为独立渲染预算）。

## 下一位 agent 可直接执行的下一步

- 裁决并修复 `xos.img`/legacy 基线断裂（上面三选一）；`make smoke` 全套在裁决前不可运行。
- 音频客体端到端套件（覆盖 `tone 440 2000`、SDK 握手、close/busy 回复不被撤销）。
- Interactium 客体输入回归（PS/2 → 服务路由 → QPA held 状态），及 aurora desktop
  测试的构建入口资产化。
- 不要误认：T1 是虚报，不要"补修"；W4 的 `queue_input` 返回值以本记录为准。
