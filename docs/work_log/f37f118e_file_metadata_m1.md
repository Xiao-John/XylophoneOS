# 文件元数据 M1：FAT 诚实子集实现

2026-11-13。依据 [file_metadata_v1](../contracts/file_metadata_v1.md) 与 #131 裁决。

## 改动

- `src/third_party/fatfs/ffconf.h`：`FF_USE_CHMOD=1`（启用 `f_chmod/f_utime`）。
- `src/shared/include/xos/file_abi.hpp`：op29 `set_metadata`、`metadata_request`、
  `stat_read_only`、`stat_metadata_bytes`，status 增加 `not_supported/-14`、
  `read_only_volume/-15`、`access_denied/-16`。
- `src/user/services/files.cpp`：
  - FAT 时间与 Unix 秒互转（UTC，2 秒量化，1980–2107 范围）；
  - `stat/fstat` 回传 RDO 标志与 mtime；`file_object` 缓存属性/mtime 供 fd 路径使用；
  - op29：句柄或路径二选一、unlinked/anonymous 拒绝、目录 `chmod` 拒绝、
    只读卷映射 `read_only_volume`、mtime 用 `f_utime`、RDO 用 `f_chmod`。
- `src/user/libc/newlib_syscalls.cpp`：`stat/fstat` 合成 `0644/0444`、`0755`、
  `uid=gid=0` 与 mtime；`access(W_OK)` 检查 RDO；实现 `chmod/fchmod/chown/fchown/
  lchown/futimens/utimensat`，`utime/utimes` 因显式 atime 诚实 `ENOTSUP`。
- `src/user/sdk/file_client.cpp` + 头：`set_metadata` 与 mtime 版 `stat_info/fstat`。
- 测试 `tests/file_metadata_guest.py` + `tests/fixtures/file_metadata/probe.c`。

## 验证

build `89d7eb53c3bcc87d`；探针在 xsh（bare）与 dash 下都输出
`FILE_METADATA_OK`（`failures=0`），资源回基线。证据：
`docs/reports/file_metadata_20261113/README.md`。

## 边界

只读卷未实测（无写保护盘）；目录 RDO 未承诺、`chmod` 目录 `ENOTSUP`；
`utime/utimes` 因 atime 恒 `ENOTSUP`；并发未压测。
