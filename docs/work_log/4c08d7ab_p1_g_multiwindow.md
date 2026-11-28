# 4c08d7ab · P1-G Mobius 独立应用多窗口闭环

2026-11-28。基线为 `6332527ab64e92371266363f41f3247717a3cac8`，独立分支
`codex/p1-g-mobius`。本组完成 P1-G 的两个独立应用绘制、damage 合成、焦点与
输入所有权、resize/close、应用故障与资源回收；没有借用旧 single-surface
记录或同一进程的两个窗口作为本次验收。共享 state/ABI 登记由主协调者维护。

## 实现与兼容

生产 Interactium 保留 wire v1 的 48 字节头、4096 字节消息及现有操作 1–14。
无新 syscall、保留字段复用、结构布局或数字分配。普通 compositor 继续独占
display v1 最终扫描面，应用通过已认证 IPC peer PID、session 和 window token
取得自己的窗口。四个 session、每 session 八个窗口标识与全局八个可绘制面
保持有界；全部前台/暂存/合成像素池共 32,640,000 字节。

`src/user/interactium/` 与 `programs/interactium_service.cpp` 增加实际 dirty
region 合成和局部 present。dirty union 来自已接受的 tile，客户端省略的 hint
不能隐藏已修改像素。tile 完整通过 premultiplied-alpha 和保留字段校验后才写
私有暂存；commit 发布，cancel 不修改前台。resize 只保留新旧交集并清掉
其余像素，同时退役旧尺寸 pending frame。移动、显隐、focus、销毁和 cursor
更新均使相应范围失效。

输入按首次 press 的 owner 保持 key-release 和 pointer capture。capture owner
隐藏/销毁后，当前持键手势被抑制至释放，不能转交另一应用。旧 hover 单测曾
以 `buttons=1` 模拟悬停，本组改为真实零按钮 hover，并单独测试 capture。

既有 `close_request` 从无效果的成功 ACK 修为仅关闭 owner 的窗口和 pending
frame，不杀进程；现有使用 `destroy_window` 的客户端路径不变。configure 的
合法 visible 标志不变，拒绝未定义 flags/title/reserved。resize 后提交旧 frame
返回失败，旧尺寸暂存不能污染新窗口。坏 framing 关闭该会话并唤醒调用方，
其他 session 继续服务。完整权限、错误和兼容说明在
[Mobius 契约](../contracts/mobius_multiwindow.md)。

新增通用 `xos/interactium_client.hpp` 校验 controller 提供的 service PID、
双端 peer、响应布局和序列，发送/接收共享 caller 原始绝对 monotonic deadline。
超时或协议故障关闭 session，不自动重放变更。每个实例由调用者串行使用；
公共头无 libc 或 newlib 私有依赖。两个 SDK builder 只引入共享
`scripts/interactium_manifest.py` 描述，保留其 producer build-only 状态。

## 实际构建和客体验收

本组使用已验证宿主 SDK 中的 GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM
3.02 与 QEMU 11.1.3。普通系统/消费者使用自身 native SDK；线程 SDK 由固定
newlib 4.6.0.20260123 原档重新构建，不混用宿主默认 glibc sysroot。
原档 SHA-256 为
`6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`。
最终系统 build ID 为 `9143113dac0b4851`；ISO SHA-256 为
`e4a3f04429b21ee88ba1e3be0b3c596bd11c511eee1ecbf55d6a8106160a1992`。

以下命令实际执行；`XOS_NEWLIB_ARCHIVE` 指调用者提供、摘要相同的固定原档，
在已验证 SDK 的非 login shell 内运行。所有输出使用各自独立目录。

```sh
python3 tests/mobius_multiwindow_host.py --output build/p1_g_host_final
python3 scripts/build_threading_newlib.py \
  --archive "$XOS_NEWLIB_ARCHIVE" --output build/p1_g_threading_newlib --jobs 2
python3 scripts/build_threading_sdk.py \
  --newlib-prefix build/p1_g_threading_newlib/prefix \
  --output build/p1_g_threading_sdk --logs-dir build/p1_g_threading_sdk_logs
python3 scripts/build_mobius_multiwindow_probe.py \
  --sdk build/p1_g_threading_sdk --output build/p1_g_threading_probe_v2
python3 scripts/build.py --output-dir build/p1_g_system_v5
python3 scripts/build_mobius_multiwindow_probe.py \
  --sdk build/p1_g_system_v5/sdk --output build/p1_g_probe_v5
XOS_QMP_TRANSPORT=pipe python3 tests/mobius_multiwindow_guest.py \
  --system build/p1_g_system_v5 --fixture build/p1_g_probe_v5 \
  --output build/p1_g_guest_v5
XOS_QMP_TRANSPORT=pipe python3 tests/mobius_multiwindow_guest.py \
  --system build/p1_g_system_v5 --fixture build/p1_g_threading_probe_v2 \
  --threading-sdk build/p1_g_threading_sdk --output build/p1_g_threading_guest_v2
python3 tests/docs_consistency.py --output-dir build/p1_g_docs_check
python3 scripts/license_audit.py --build build/p1_g_system_v5
```

| 实际检查 | 结果 |
| --- | --- |
| 四套 host model/transport/demo/multiwindow | ASan/UBSan 通过，新增套件 106 条断言；host GCC 14.2.0 |
| 普通 SDK 两个独立 PID | 15 组通过，11 个额外 ownership/protocol 负例包含在其中 |
| 重新构建线程 SDK 的 POSIX 消费者 | 16 组通过；实际使用自有 `crt0_posix.o`/libc/libm/libxos，另测 pthread/TLS/errno/join |
| 两个客体的最终资源 | 均精确恢复 129789 free pages / 2 tasks / 0 completions |
| 文档与 ABI 一致性 | 2337 本地链接、79 syscall 登记、73 历史源通过 |
| 登记许可材料与 SDK 副本 | 10 组通过，0 active open；不扩写为完整法律审计 |

每个 guest 都包含真实屏幕像素断言、PS/2 焦点及拖拽输入、按键释放保留 owner、
私有暂存与 cancel/commit、移动和 resize、右应用 pending frame 中真实 `ud2`
故障、左应用继续可操作、正常 close、服务死亡、活着但不响应的服务遵守原
五秒 deadline、同一 display 下 compositor 重启以及旧 `gfxdemo` 回归。
普通和线程配置各九张实际截图与完整串口 gzip 单独保存。

## 失败尝试与证据

早期 candidate、READY 分段输出解析失败、构建途中测试改变导致输入校验拒绝、
崩溃后背景断言采到 cursor，以及线程 fixture 初次错误请求未导出的 `crt0.o`
均保留在本地并在 `attempts.json` 如实记录。最后修正启动 recipe 使用该线程
SDK 实际 POSIX CRT 与匹配运行库，没有向其拷入普通 CRT。截图失败发生在实际
故障、另一应用保留和精确资源回收之后；最终选择 cursor 外的坐标验证。
host LSan 因 ptrace 无法枚举线程而不可用，显式禁用；未把它标为通过。

持久证据为 [P1-G 报告](../reports/p1_g_multiwindow_20261128/README.md)。新目录
使用平铺根 `manifest.json`；公有叶子互不内嵌哈希。公开 JSON 是明确标记的
派生摘要，省略机器命令路径，保留原始本地回执身份和真实检查结果。2305 个
系统输入及 261 个线程 SDK 输入在运行后和导出时再次核对。未改历史报告。

公开前 index 路径检查为 `PUBLIC_READY`，无 OPEN、UNVERIFIED 或 DOUBTFUL。
本目录平铺索引 32/32 校验通过，仓库 manifest 扫描将其列为 compliant；
全仓扫描仍因既有发行/Qt 报告的非平铺或无效历史索引失败，详细名单保留在本组
`validation.json`，没有把全仓失败写成通过，也没有改写这些历史目录。

## 限制与交接

本次没有重建 Qt QPA/Qt 包，没有运行 C++ 标准运行库 GUI、installed
Mobius/ClarkE 组合、实体 GPU、SMP、glass blur 或长期 stress。Qt 现有合法
create/tile/commit/destroy wire 路径保留，但其整包资格需独立新证据。
compositor 空闲时使用 10 ms monotonic sleep；既有 display/命名 IPC 尚无
共同 wait set，不宣称事件驱动统一等待。此 PR 不新增窗口装饰、GPU 加速或
标准库线程内并发共享一个 client 的保证。

主协调者可据本次 commit 发布独立 P1-G PR，并将既有 Interactium wire 命名空间
和本组资格入口写入公共 registry/state。合并其他阶段代码后仍须对受影响组合
做真实回归，不能把本组精确输入的资格直接转移给不同系统。下一独立工作为
P1-K4 named installed DHCP/TLS 与 dynamic GNU 组合，另建分支和证据。
