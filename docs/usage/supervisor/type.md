# `type`

在Xsh输入`type <command>`，显示内建命令、exd固定别名或外部命令最终路径。
它采用与实际外部启动相同的候选检查与PATH选择，检查时不创建任务。
例如`type dash`显示`dash -> /usr/bin/dash`；`type exd`显示其为exec-driver别名。
当前没有`--all`，预检结果不保证未来启动时的资源/授权或文件内容保持不变。

[返回索引](../index.md)
