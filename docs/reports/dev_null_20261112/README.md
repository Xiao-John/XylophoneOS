# /dev/null 客体证据（2026-11-12）

来源：端口反馈账本 `PL-0006`（lz4 `-t` 因缺少 `/dev/null` 失败）。

## 实现

文件服务将 `/dev` 视为虚拟目录、`/dev/null` 视为 null 对象：

- `stat("/dev")` 返回目录；`stat("/dev/null")` 返回大小 0 的普通文件。
- `open("/dev/null")` 返回真实句柄（可跨 spawn 继承）；`write` 丢弃并返回长度，
  `read` 返回 0，`lseek` 推进逻辑偏移，`ftruncate` 成功且不改变大小，`close` 不碰 FatFs。
- 路径比较同时接受服务内的无前导斜杠形式（`dev/null`）。

## 验证

- build `26161cda4ebf8109`（kernel 721752 字节）。
- `tests/dev_null_guest.py`：`DEV_NULL_OK`，覆盖 open/write/lseek/read/stat/fstat/close，
  以及 `/dev/not-null` 返回 `ENOENT`、`O_CREAT|O_EXCL` 对已存在的 `/dev/null` 返回
  `EEXIST`（不把“创建成功”报给调用方）；资源计数回基线。
- 用线程版 lz4 在客体复测（同一 ISO）：

```text
/tests/lz4mt -T2 -1 -f /sample.txt /t.lz4
Compressed 3960 bytes into 391 bytes ==> 9.87%
/tests/lz4mt -t /t.lz4
/t.lz4                         : decoded 3960 bytes
test_rc=0
/tests/lz4mt -d -f /t.lz4 /t.out
dec_rc=0
```

`lz4 -t` 不再报 `/dev/null: No such file or directory`。

## 未覆盖

- `readdir("/dev")` 仍走 FatFs，不会列出 `null`；`open("/dev/null")` 与 `stat` 不受影响。
- `/dev/null` 在 `fstat` 里按普通文件报告（`st_mode` 非字符设备）。
- 其它设备节点（`/dev/zero`、`/dev/tty` 等）未实现。
