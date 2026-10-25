# `elftest`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `xsh>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

在真实 ring3 装载服务内跑 24 个确定性解析边界：正确头、坏 magic/machine/
ET_DYN、INTERP/DYNAMIC/TLS、文件/地址溢出、filesz>memsz、对齐、页重叠、入口与页上限。
通过打印 cases=24 result=pass resources=stable，不创建子任务。
宿主还使用 ASan/UBSan 做同组边界、截断与确定性变异；这不是完整 ELF 合规证明。

[返回索引](../index.md)

