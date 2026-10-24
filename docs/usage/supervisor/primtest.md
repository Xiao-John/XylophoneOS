# `primtest`

- 控制台：用户态 supervisor，先在 `xos64>` 输入 `run`，提示符 `sup>`。
- 彩蛋依赖：无。
- 实现：`src/user/programs/supervisor.cpp`，装载机制见 `docs/e04_loader_sdk.md`。

监督服务直接测试构造原语：越界地址、W+X、内核复制源、重复映射、坏初始入口、
重复 abort/旧句柄、任务槽上限与 65536 用户页上限（256 MiB），然后取消所有测试构造。
只有真实资源计数恢复才打印 rollback=stable。需要有空闲任务槽；若被后台任务
占满，先 kill/wait 清理。本命令不启动测试半成品，不提供普通程序的构造权限。

[返回索引](../index.md)


E08-1 另外输出 page_pressure 实际页数与 tick，随后逐层回收并对比真实空闲页。
