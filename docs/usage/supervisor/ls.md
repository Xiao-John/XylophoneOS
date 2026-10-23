# `ls`

- 控制台：用户态 supervisor（`xos64>` 输入 `run`，然后 `sup>`）
- 语法：`ls`
- 实现：`src/user/services/file_ui.cpp`，协议见 `docs/e05_file_service.md`

列出工作盘 FAT16 根目录中的文件（8.3 短名，显示大写）：

```text
HELLO.ELF size=9128 version=0
NOTE.TXT size=34 version=0
```

没有目录/层级；顺序来自 FAT 目录。正常 `sync` 后重启仍存在。
最多 4 个文件，每文件 24 KiB；`version` 当前固定为 0。

错误：文件服务不可用时打印 `[files] ... error=...`，不会伪造空列表或成功。
