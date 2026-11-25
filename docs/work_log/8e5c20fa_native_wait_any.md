# Native wait-any prerequisite for glibc process control

2026-11-25 · 基线 `5984573`；本模块独立实现 syscall 20 的认证任意子进程
等待，供后续 glibc `waitpid(-1, ...)` 和 dash 使用。

## 接口与实现

按共享接口协调结果，third bit0 继续表示非阻塞，新增 bit1 表示 wait-any，
此时 first 必须为 0。原精确 PID 的 flags=0/1 保持原语义，48 字节
`process_status` 布局保持。专项契约、ABI 登记、共享头、SDK `wait_any`
helper 和 SDK process_extensions 元数据一起更新；没有 libc PID 清单。

完成记录增加内核内部 `published` 标记，只在 start 或 fork commit 成功后
对 wait-any 可见。选择按真实 parent 身份进行；精确等待者和已经唤醒但尚未
copyout 的等待者保留领取权。消费、child CPU 计入和销毁记录只发生一次。
copyout 失败归还领取权；消费最后一份记录也唤醒其他任意等待者返回无子进程。
父退出、cancel、building 回滚和 exec 继续使用既有生命周期。

## 实际结果

生产 `tasks.cpp` 函数提取测试运行普通构建与 ASan/UBSan，两轮各 **8 组
PASS**。覆盖 flags、失败输出保持、building/被取消 builder 不可见、精确与
任意竞争、两个任意等待者、延迟 copyout 领取权、copyout 失败归还、唯一 CPU
累计、父退出 pin 回收及跨父认证。旧 `5984573` 实现实际在 wait-any 非阻塞
场景失败，证据保留。

真实 QEMU 最终运行 **27 次（9 个模式 × 3 轮）、10 组检查 PASS**：

- 顺序阻塞/非阻塞、空结果及输出保持，独立应用不能领取同级子进程。
- fork prepare 不可见，真实 files clone + fork commit 后可等待。
- exact/any、two-any、最后 child 被另一 waiter 消费后的唤醒与唯一交付。
- 正常退出、真实 `ud2` fault 和 native kill 的 PID/outcome 对应。
- 同 PID 成功 exec 后，新映像未获得 child PID 清单仍回收旧映像的两个 child。
- 普通父退出 orphan 和 Escape 前台取消；每次回到同一资源基线：
  129815 空闲页、2 个活动任务、0 份完成记录。

exec receiver 使用现有已实现 startup-v3 的 newlib CRT，仅作内核机制的
独立回归输入；此模块不向公共接口或实现引入 newlib 私有结构。glibc 出站
wrapper 与同其运行库组合的客体验收另行交付。

## 复现与来源绑定

```sh
python3 tests/kernel_process_wait_race_test.py --output build/wait_any_host
python3 tests/kernel_process_wait_race_test.py --sanitize --output build/wait_any_sanitized
python3 scripts/build.py --output-dir build/wait_any_system_final
python3 tests/process_wait_any_guest.py --system build/wait_any_system_final --output build/wait_any_guest_final
```

宿主 GCC 14.2.0；preview 工具链 GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02；QEMU 11.1.3 Debian `1:11.1.3+ds-2`（仓库锁是 11.1.2，
本环境的版本差异保留）。系统 build ID `44d163ec92cfd57e`，内核 821400
字节。runner 在前后核对完整系统源码/产物、SDK 清单、链接输入与夹具，
使用普通串口，关闭 QMP；工作盘是测试专用 512 MiB FAT32。

[冻结报告](../reports/process_wait_any_20261125/manifest.json) 保存普通与
sanitizer、旧实现失败、最终 guest 串口、工具/ELF/SDK/系统元数据及来源散列。
公开报告是脱敏派生版，保留原始报告散列，不改绑此前证据。

早期夹具因机制线程头不在普通 SDK 中而编译失败；修正为测试私有 include，
显式记录该头与机制线程 archive。随后旧系统绑定正确拒绝改变过的 runner，
最终重新构建系统后通过。两个失败保留，未当作验收成功。

LeakSanitizer 因宿主 ptrace 限制未运行；ASan/UBSan 实际运行。进程组等待、
停止/继续与通用信号投递不在本扩展范围。后续 glibc process 与活跃退出、
generic IPC exec 撤销组合后应重建新系统重新验收，当前结果绑定本基线。
