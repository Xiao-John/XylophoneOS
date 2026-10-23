# `rm <file>`

- 控制台：用户态 supervisor
- 语法：`rm <file>`
- 实现：`src/user/services/file_ui.cpp`

删除工作盘文件并释放名字槽：

```text
[files] removed note.txt
```

若文件仍有打开实例，返回 `busy`，不会静默关闭别人的游标。不存在返回
`[files] remove error=-1`。删除后执行 `sync` 才保证落盘；删除不压缩存储。
