# 0138：终端服务模式基础

2026-10-30。检查锁定的 ncurses 6.5 后，确认其实际路径会调用 termios 设置，
包含 `VMIN=0,VTIME=1` 的短等待和 `TCSADRAIN`；不能只提供无限阻塞读或声称
空模式桩满足依赖。本组先实现服务端受控应用的真实原始模式状态与三类读取：
`(VMIN,VTIME)=(1,0)` 阻塞到至少一字节、`(0,0)` 立即返回、`(0,n)` 等待 n 个
100ms 后无数据返回零；其他标志或组合明确拒绝。模式属于应用会话，结束时复位；
服务检查完整请求后原子更新。客户端增加模式 get/set 和 `read_mode`。
细节见[终端控制契约](../contracts/terminal_control.md)。

宿主服务探针覆盖模式校验、即时空读和即时有数据读取；客户端模拟覆盖模式读取、
更新、拒绝非法模式和空读结果。原有模拟通过，命令见 0134/0135。
`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_terminal_modes_v2_20261030` 通过，build ID `50e537c9bf85943a`，terminal
ELF SHA-256 `c67826e3bf32612f436544aaef6a6eb508cd03ba32a3b3594a9bbb26b6ee2830`；
构建早于本文档更新。`git diff --check` 通过。

未实现 POSIX termios 头与 libc 绑定、TCSADRAIN 发送排空、规范模式、回显、信号或
其他 VMIN/VTIME 组合；libc 普通 read 尚未调用 `read_mode`。时间精度、读取与模式
竞争、故障和硬件行为未客体验证。下一步实现诚实的 POSIX 映射和排空路径，再接入
ncurses；全部相关修改提交后执行客体验收，W1/W2 尚未完成。
