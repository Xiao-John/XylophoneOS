# 终端可读等待与受限 select

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

0144 的客体探针在首次方向键读取返回失败。ncurses 目标配置此前既没有 select
也没有 poll，定时等待无可用实现；本组增加不消费输入的终端服务可读等待及
单终端读取描述符的 libc select。该子集对其余组合明确返回错误，不宣称通用多路复用。
服务用原有队列锁和 wait-word 交换检查/等待，避免检查与中断之间丢失唤醒；
超时使用单调时钟，控制请求可中断。协议和局限见 terminal_control.md。

`c++ -std=c++20 -Wall -Wextra -Werror -pthread -I src/shared/include
-I src/user/include tests/fixtures/ncursesw/terminal_service_host.cpp -o
${XOS_SCRATCH}/xos_terminal_service_select_host && ${XOS_SCRATCH}/xos_terminal_service_select_host` 通过，
覆盖空队列超时及反复检查不消耗已有字节，属宿主模拟。SDK 候选
`${XOS_SCRATCH}/xos_select_utf8_sdk_v2_20261101` 树 SHA-256
`212b0e17e366f0589cb9609516d621984f0947e22d528f2dd4b0b374737e426b`，
仍为 built_unverified。第一次系统构建因把 select 放入已有 libc 大对象而使
`libc_hello` 超出镜像限制失败；将其拆为独立归档成员后专用构建通过，
build ID `285651f6155f743b`。旧 candidate 不再用于本组目标验证。

该实现尚未在真实客体运行，不证明方向键故障已解决；多描述符、写就绪、线程、
生命周期、故障及 W1/W2 的其他要求仍待实现或验证。提交源码后须重建匹配候选和
系统，在干净提交快照运行客体探针并保留结果。

提交 `4234727` 后在隔离干净快照重新构建系统 `d3cadca31e99d52a`，以匹配 SDK、
ncurses 及 terminfo 运行 `tests/ncurses_guest_probe.py`，两个受限探针通过：红色中文
窗口、左方向键和中文输入输出，以及未知终端拒绝、80×24 尺寸与重入。系统 ISO
SHA-256 `be7b0d06bd8a12ee7a4e543a74c58c742b78992855dfcbdb161465f0c1f5f48f`；
SDK 树 `17bf29c30df01304f064079da13e70919f09e70355334c9dc68c9ef4a35452de`；
ncurses 归档 `f9083ccca7f0f5b1a271b8e9fe3ea9df85f60b924d63490bd6847ec05e7f1b1d`；
串口 `1ee83f2a8d32f092c80cee287e39a17d85eedec80a02399d405699c3b8bb91c8`。
回执和串口日志分别位于隔离工作区 `build/w2_select_4234727/ncurses_guest_probe_report.json`
和 `build/ncurses_guest_probe_serial.log`。这些结果不扩展为完整 W1/W2 资格。
