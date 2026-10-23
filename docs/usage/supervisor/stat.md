# `stat <file>`

- 控制台：用户态 supervisor
- 语法：`stat <file>`
- 实现：`src/user/services/file_ui.cpp`

显示文件大小和内容版本：

```text
note.txt size=34 version=2
```

当前 `version` 固定为 0；替换/删除期间若文件被打开会返回 busy，读取端用
open/stat 大小校验保证快照稳定。它不是 FAT 的 inode、时间戳或权限元数据。
文件不存在返回 `[files] stat error=-1`。
