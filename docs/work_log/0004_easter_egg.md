# 0004：Guo YePeng 进入内核，错误仍然优先

日期：2026-10-23（Asia/Shanghai）。负责：主 agent。状态：完成。

## 范围与结果

用户要求给 TUI/调试控制台加无害特色，并把朋友 Guo YePeng 的名字放进去；用户
明确喜欢 “did not panic (yet)” 这句小幽默。本组只改控制台文案和只读命令，不改
错误语义、不加随机故障或延迟，并沿用 `config/x86_64_bios.json` 的 `easter_eggs`
总开关。

- 启动横幅：XOS 版本、位数、Guo YePeng 名字与 “did not panic, yet”。
- `guo`：仪式性问候，`status=did_not_panic_yet`。
- `joke`：五条确定性冷笑话循环，不使用随机数。
- `about`：版本、构建 ID、致谢；明确 bug 仍归主 agent。
- 关闭 `easter_eggs` 时横幅、帮助项和三个命令都不出现，`guo` 回到
  `ERROR: unknown_command`。

## 文件

- `src/kernel/core/console.cpp`：横幅、`guo`/`joke`/`about`、帮助文本与
  `#if XOS_EASTER_EGGS` 条件编译。
- `tests/kernel_smoke.py`：彩蛋开启时检查横幅与三条命令，检查项从 17 增至 18。
- `README.md`、`docs/state.md`、`docs/toolchain.md`、`docs/work_log/0003_*.md`
  的交接说明同步。
- 没有修改异常、内存、页表或启动代码；没有触碰 `localpilot/`。

## 选择与原因

- 所有彩蛋集中在一个文件、一个编译开关下，默认随 `easter_eggs` 开启；关闭后
  连命令都不注册，避免留下可被误用的旁路。
- 笑话用固定数组按调用次序循环，不引入 RNG、时间或额外状态；重复运行结果一致。
- 横幅只在内核启动检查全部通过之后出现；诊断行仍在前面，错误不会被玩笑遮住。
- `about` 里保留真实构建 ID，彩蛋不伪装版本或验证结果。
- 文案只使用 ASCII，避免 VGA 文本模式代码页问题；不改变串口协议。

## 实际验证

构建 ID：`8e755d51d346e83d`。`make smoke`：

```text
PASS: 6 checks | build 8e755d51d346e83d
PASS: 18 E02 checks | build 8e755d51d346e83d
```

新增检查 `easter_egg_banner_and_guo_commands` 实际等待横幅
`Guest star: Guo YePeng (did not panic, yet)`，并执行 `guo`、`joke`、`about`
检查返回文本。`guo` 实际输出：

```text
[guo] name="Guo YePeng" role="friend, chaos consultant"
[guo] status=did_not_panic_yet ego=+1
[guo] tip=if it breaks, check the GDT first
```

关闭验证：临时把 `config/x86_64_bios.json` 的 `easter_eggs` 设为 false 后重建，
启动日志与提示符中没有 `Guo YePeng`/横幅，输入 `guo` 返回
`ERROR: unknown_command`；随后恢复 true 并重建，构建 ID 回到
`8e755d51d346e83d`，产物哈希与开启构建一致。

产物：

- `kernel.elf` 127,208 字节，SHA-256
  `c809bbdf0a96067561ea4c33d3d8d22be9a71aaaa480210f721712cd7a9a35f8`。
- `kernel.bin` 16,392 字节，SHA-256
  `4e7170828b259e23b3bc657e0a5b619562ccb2152568f177b925625eca29dc8f`。
- `xos.img` 1,474,560 字节，SHA-256
  `08238c3fbe3624e37ff4d2319c86d18d0bf75ec42789579e06599a50a261f463`。
- `real_mode.img` SHA-256
  `254759a0c42cf0ee5ce6e198019069b7bb40d58e89a7c0db39b0517a0da12557`。
- 截图：`build/kernel_screen.png`（实际 VGA 帧缓冲，已查看）。

## 未运行与限制

- 没有为彩蛋增加独立自动化用例覆盖 “关闭构建下 help 不列出命令” 的完整集合；
  已手工验证横幅不出现且 `guo` 被拒绝，关闭构建未跑完整 smoke（会改变构建 ID）。
- 彩蛋只有英文 ASCII 文案；没有随机笑话、动画、声音或交互小游戏，也不应为了
  一个梗扩展子系统。
- 不改变任何错误处理、内存、权限、时序或验证结果；不是安全边界的一部分。

## 下一步

E03 不变：ring3、每任务地址空间、任务切换与故障回收，再补定时抢占与最小 IPC。
彩蛋保持默认开启、可关闭；后续 TUI/终端迁往用户态时，文案可一起搬走，不能把
内核彩蛋当成终端 ABI。
