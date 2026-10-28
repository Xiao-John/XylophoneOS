# 0074：ncursesw W0/W1 勘查与终端契约草案

2026-10-28。用户要求完成 W1，并要求所有相关改动提交后验收。本组在
`codex/ncursesw_w1` 开始，当前尚未完成 W0、未实现或验收 W1，不得声明通过。
只读子代理检查终端与目标 newlib；主 agent 新增[终端工作契约](../contracts/terminal_w1.md)
及 `tests/fixtures/ncursesw/wide_locale_probe.c`，该探针尚未在客体执行。

已核当前仓库 newlib 4.6.0.20260123 的 `newlib.h` 未定义 `_MB_CAPABLE`；存在宽字符函数
符号不证明 UTF-8 locale。旧 SDK `build/input_edit_final/sdk` 的 libc.a 与当前 vendored
libc.a SHA256 均为 `283fa07ad205c80af92e955a91da027435d8a8a90cb7e27933f57925cc5baa22`，
头文件 newlib.h 均为 `f83c3134b15f42b48bb595259c43ab971aac50f7d1d8a21dd32944980d13380b`。
旧 SDK 的符号链接实验在临时目录成功，但未运行且不是当前完整 SDK 或客体资格。
该 SDK 的 `<termios.h>` 编译探针因缺少 `sys/termios.h` 失败；当前仓库对应头目录
同样缺少该文件，需同时设计公开类型和真实实现，不能仅补函数桩。

实际串口路径：`timer_entry` 前台取消会消费 ESC，影响方向键；后台/前台共享 console
读路径。COM1 IRQ 接收关闭，`debug_peek` 使用单字节轮询；console 不支持 pipe_wait 的
阻塞唤醒，旧 `sys_read` 空闲可返回 0。PIC 当前初始化掩码和显示输入掩码均需与 IRQ4
协调。其余输入/等待/授权、fork/exec、超时与生命周期依赖记录于工作契约，不能以
假 termios 或定时轮询冒充已完成。

ncurses 6.5 候选从上游作者镜像 `https://invisible-mirror.net/archives/ncurses/ncurses-6.5.tar.gz`
下载至临时目录，实测 SHA256 `136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6`；
未验签或逐成员审许可，尚非正式 source lock。源码包含可配置的 poll/select、SIGWINCH、
尺寸 ioctl、mbrtowc 与 wcwidth 路径；目标实际构建及各路径仍须核查。

本轮未分配 syscall、修改运行时代码、替换 SDK、构建系统或运行验收。
下一步完成 W0 source lock 与实际调用列表，确定通用终端对象及 UART/等待边界、预留 ABI；
实施可复用服务、SDK 和多字节 newlib profile 后提交，再运行完整客体验收。
