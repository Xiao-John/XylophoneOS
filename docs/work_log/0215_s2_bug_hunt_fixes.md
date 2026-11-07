# 0215 Season-2 报告修复：安装事务、rename 恢复、readdir、工具缓存

输入为 CONTEST 的 5 份 Season-2 报告；按去重后的独立问题修复，未重复已修项。

## 代码修复

- `files.cpp`：写越界零填充失败回滚原长度；rename 备份恢复失败时保留 journal（不再留
  `XOSBAK.TMP` 孤儿）；journal 改为临时文件完整同步后 rename 发布；`same_path_object`
  改为三态、stat 错误返回 EIO；目录祖先检查遇 I/O 错误拒绝；仅大小写不同的 rename
  调用 FatFs 更新目录项；恢复按 staging 路径冲突判定而非全局 busy。
- `file_ui.cpp`：所有成员先做 SHA-256 预检再落盘（后序成员坏摘要不提交前序成员）；
  成员名按 `name_len` 拒绝内嵌 NUL；staged 容量 8→16 且安装成功后才登记；已存在目标
  哈希磁盘文件本身；非 bundle 载荷必须是 ELF；marker 绑定启动载荷 SHA-256；暴露
  `bundle_install_ok()`，失败时不进入包安装/写 marker。
- `supervisor.cpp`：包安装改用幂等 `xypm ensure`；marker 写入与维护清理失败不再报成功；
  bundle 未完整安装时不安装包。
- `xypm`：新增 `ensure`（未装则 install、同摘要 no-op、不同摘要 upgrade），支持部分
  成功后重试。
- `newlib_syscalls.cpp`：readdir 合成 `.`/`..`，rewinddir 重置。
- `xos_bundle.py`：名称区必须紧凑分区；CLI 将 JSON/文件/字段错误转为 `REJECT`。
- `make_iso.py`：拒绝重复（大小写折叠）和非法根文件名。
- `work_disk.py`：缓存 stamp 同时记录源码摘要与二进制 SHA-256，校验普通文件/属主。
- `user_build.py`：supervisor/file_ui 使用 `-Os`，内核 512080 字节，保留 legacy `xos.img`。

## 误报/过期项

- contest-4 S2-1..S2-4（spawnp 边界、JSON INT64_MIN、diskio 回绕、erase_last 注释）
  已在 0213 修复，当前基线不可复现，属过期报告而非新缺陷。
- contest-1/2/5 的 8 项容量、marker、staged 提前登记、NUL、retry 等互为重复，按合并后
  的单一问题修复。
- contest-1 S3-08（cwd 文本路径未绑定 inode）属实但属架构性限制，登记 FS-08，未在本轮
  改动 ABI。
- contest-3 “已有目标摘要匹配时载荷未验证”属实，由统一预检摘要修复。

## 证据（2026-11-07，build 4bd9c9e9b18f68bc）

```text
tests/file_semantics.py            15 cases
tests/file_posix_guest.py          11 checks
tests/test_xos_bundle.py           26 tests
tests/make_iso_names.py            OK
tests/work_disk_cache.py           OK
tests/xypm_host_cache.py           OK
tests/xypm_json_cases.py           7
tests/fatfs_diskio_cases.py        10
tests/file_smoke.py                PASS 8
tests/runtime_smoke.py             PASS 5
tests/file_recovery_faults.py      21
tests/file_recovery_guest.py       passed
tests/iso_bundle_install/reboot/daily/reject  passed
tests/bundle_preexisting_digest.py passed
tests/bundle_installer_reject.py   bad-name/reserved1/bad-magic/non-elf-legacy/later-digest
tests/bundle_marker_identity.py    passed
```

未运行：真实共享 /tmp 跨用户攻击、真实满盘、完整 make smoke、xypm 真实 ensure 的客体
故障注入（fake xypm 验证了 marker 路径）。工作记录 0214 的已知“运行时失败可能保留前序
已提交成员”仍成立。
