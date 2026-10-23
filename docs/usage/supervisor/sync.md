# `sync`

- 控制台：用户态 supervisor
- 语法：`sync`
- 实现：`src/user/services/file_ui.cpp`、`src/user/services/files.cpp`

对所有以写方式打开的文件执行 FatFs `f_sync`，再对块设备执行 `CTRL_SYNC`
（ATA FLUSH CACHE）。只有全部成功才输出：

```text
[files] sync=ok
```

失败输出真实错误，例如 `[files] sync error=-3`。看到 `sync=ok` 后再停止
QEMU，正常重启后文件内容应仍在。

边界：这只覆盖本实现的文件缓存/块设备 FLUSH，不是任意硬件突然掉电下的
事务原子性证明；没有 ACPI 关机、fsck 或坏扇区恢复。工作盘缺失/只读时
返回错误，不退回 RAM、不格式化。
