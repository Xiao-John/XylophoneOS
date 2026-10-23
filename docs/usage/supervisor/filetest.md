# `filetest`

- 控制台：用户态 supervisor
- 语法：`filetest`
- 实现：`src/user/services/file_ui.cpp`

在已有 FAT16 工作盘上运行文件服务的确定性自检；工作盘缺失/挂载失败时
命令返回错误，不会退回 RAM：

- 创建测试文件，短读与 EOF；
- 对同一文件打开两次，验证游标互不共享；
- seek 回绕、读写方向；
- 部分写入的实际字节数；
- 超容量替换被拒绝且旧文件保留；
- 无效句柄被拒绝；
- 删除与清理。

通过输出：

```text
[filetest] result=pass short=read/eof handles=independent capacity=preserved partial=write invalid=rejected
```

失败只在检查不成立时打印 `result=FAILED`；不会用成功文案掩盖。
自检会创建并删除 `t1`，不触碰其他用户文件。
