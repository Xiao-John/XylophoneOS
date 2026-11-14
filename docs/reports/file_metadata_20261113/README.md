# 文件元数据（FAT 诚实子集）客体证据（2026-11-13）

| 项 | 值 |
|---|---|
| 契约 | [`docs/contracts/file_metadata_v1.md`](../../contracts/file_metadata_v1.md) |
| 线格式 | file wire v2；新增 op29 `set_metadata`；`stat/fstat` 扩展 RDO 位与 mtime |
| FatFs | `FF_USE_CHMOD=1`；mtime 2 秒量化、UTC；RDO 由 `f_chmod` 设置 |
| 构建 | build `89d7eb53c3bcc87d`（kernel 813208 字节） |
| 测试 | `tests/file_metadata_guest.py`（`metadata_unit` + `metadata_dash` + 资源回基线） |

## 客体原始输出（节选）

```text
create=1
write=1
stat_file=1
chmod_readonly=1
stat_readonly=1
access_w_denied=1
open_write_denied=1
chmod_writable=1
access_w_ok=1
open_write_ok=1
chmod_0600_notsup=1
chmod_setuid_notsup=1
open_before_chmod=1
chmod_with_open_handle=1
open_after_chmod_denied=1
fstat_path_chmod_visible=1
chmod_restore=1
futimens_bad_nsec=1
combined_mask_rejected=1
chown_noop=1
chown_other_notsup=1
utimensat_mtime=1
mtime_readback=1
explicit_atime_notsup=1
double_omit=1
futimens_mtime=1
fstat_mtime=1
fchmod_readonly=1
fstat_readonly=1
fchmod_writable=1
create2=1
unlink2=1
unlinked_fchmod_notsup=1
mkdir=1
stat_dir=1
dbchmod_dir_notsup=1
rmdir=1
cleanup=1
failures=0
FILE_METADATA_OK
```

同一探针在 `dash /tests/meta.sh` 下重复通过；两次运行后进程/对象资源回到基线。

## 覆盖

- 文件 `stat` 投影 `0644/0444`、`uid=gid=0`；目录 `0755`。
- `chmod` 可表达往返；`0600`、`04755` → `ENOTSUP`；目录 `chmod` → `ENOTSUP`。
- RDO 后 `access(W_OK)`/`open(O_WRONLY)` → `EACCES`；恢复后成功。
- `chown(-1,-1)/(0,0)` 无变更成功；其它值 `ENOTSUP`。
- `utimensat` 写 mtime（`1700000000` 回读一致）；显式 atime → `ENOTSUP`；双 `UTIME_OMIT` 校验对象。
- `futimens`/`fchmod`/`fstat` 走 fd 路径；unlink 后 `fchmod` → `ENOTSUP`。
- xsh（bare probe）与 dash 两条路径。
- 已打开可写句柄不绕过后续 `chmod 0444`；`fstat` 能立即看到路径形式 `chmod`；
  纳秒越界 → `EINVAL`；RDO+MTIME 组合请求 → `ENOTSUP`。

## 未覆盖

- 只读卷/写保护介质未在此镜像上实测（无写保护盘）；代码路径保留 `EROFS` 映射。
- 目录 RDO 未承诺：`chmod` 目录直接 `ENOTSUP`，未验证 FatFs 目录只读的写隔离。
- `utime/utimes` 因显式 atime 恒 `ENOTSUP`；需要时改用 `utimensat` 的 `UTIME_OMIT`。
- 并发/多会话下的元数据竞争未做压力测试（文件服务单线程串行）。
