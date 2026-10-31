# dash后续路线

普通命令与创建权限继承的下一阶段见[双Shell启动优化计划](shell_launch.md)，尚未实现；
该计划同时覆盖xsh、SDK和进程机制，不以增加工具名称特例解决。

2026-10-27。dash0.5.13.5的A/B/C受限gate已有证据，xsh保留默认入口。
当前范围见[Shell实现](../implementation/shell.md)，证据见[主题摘要](../history/shell.md)。

| 后续工作 | 底座依赖 | 独立验收 |
|---|---|---|
| 后台、trap、wait与信号相关行为 | PX1信号/完整等待、进程生命周期 | 不同退出/信号/中断/取消路径，权限与回收，不靠语法解锁冒充 |
| 交互作业控制 | PX2 session/pgrp/TTY/termios | Ctrl-C/Ctrl-Z、前后台切换与停止/继续、终端恢复、xsh救援 |
| 更完整FD重定向/标准脚本边界 | SDK支持与兼容准入 | 参数/环境/FD标志、开关顺序、失败回滚，旧CRT显式拒绝 |
| Make增量与标准工具 | 文件时间戳/路径及各工具接口 | 真实改源后只重建依赖、错误不误报成功，GNU扩展另列 |

复用上游解析/执行结构，移植补丁集中在平台层；不把限制实现变成静默成功，不为Shell
引入ELF解析入内核或工具名授予构造权。B2共享打开描述不能用path重开模拟。
单线程fork/exec不推出线程profile支持；POSIX基础/选项按[子集契约](../contracts/posix_subset.md)
逐项审计。参考dash行为或宿主对照仅作指定输入对照，不替代完整标准符合性。

日常独立工具统一按[daily_utilities.md](daily_utilities.md)补齐；命令实现和安装是独立交付，
不靠扩充xsh内建或更换dash默认入口解决。DU1/2已有实现与定向组合证据，完整资格与后续交付见[state](../state.md)。
