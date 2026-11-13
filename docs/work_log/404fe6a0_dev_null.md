# 文件服务：`/dev` 虚拟目录与 `/dev/null`

2026-11-12。来源：端口反馈账本 `PL-0006`。lz4 的 `-t` 需要打开 `/dev/null` 写空输出，
而客体没有该路径，导致自检模式失败。

## 改动

- `src/user/services/files.cpp`：新增 `is_dev_directory`/`is_null_device`（同时接受服务内
  无前导斜杠形式）；`op::stat` 对 `/dev` 返回目录、`/dev/null` 返回零长文件；`op::open`
  为 `/dev/null` 建立 null 描述符；`read` 返回 0、`write` 丢弃并返回长度、`lseek` 维护
  逻辑偏移、`ftruncate` 成功、`cleanup_description` 不调用 `f_close`。
- `tests/dev_null_guest.py` + `tests/fixtures/dev_null/probe.c`：覆盖 open/write/lseek/read/
  stat/fstat/close 与 `/dev/not-null` 的 `ENOENT`，并检查资源计数回基线。
- 证据：`docs/reports/dev_null_20261112/README.md`（含 `lz4 -t` 复测）。

## 边界

- `readdir("/dev")` 不列 `null`；`fstat` 按普通文件报告。
- 仅实现 `/dev/null`；`/dev/zero`、`/dev/tty` 等未做。

## 验证

```text
python3 scripts/build.py            -> build 41e919e2ccb9c253
python3 tests/dev_null_guest.py     -> passed（dev_null_behaved, resources_restored）
客体 lz4 -T2 压缩后 -t              -> decoded 3960 bytes, test_rc=0
```
