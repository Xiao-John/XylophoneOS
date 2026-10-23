# `help`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `sup>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

显示实际的 ps、kill、images、exec、spawn、wait、stats、primtest、elftest、
ls、cat、stat、rm、edit、filetest、sync、exec-file 命令。
当前附加帮助参数会被忽略，不提供按命令检索。

[返回索引](../index.md)

