# `filetest`

在当前工作盘创建并清理 `t1`，真实验证短读/EOF、两个独立游标、read-only seek
越过 EOF 后返回实际位置、写入实际字节、打开期间替换拒绝、旧内容保留、无效句柄。

通过输出 `[filetest] result=pass ... locked=preserved write=actual invalid=rejected`。
容量不足另由临时满盘集成测试验证；E08-1 已移除旧 4 文件/24 KiB 人工上限。
本命令会操作 t1，勿把唯一资料存成该测试名。
