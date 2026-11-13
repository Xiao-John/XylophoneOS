# 文件元数据契约 v1（FAT 诚实子集）

2026-11-13。状态：**M0 契约与 ABI 占号；尚未实现**。依据 [权限与 POSIX 元数据裁决](../plans/permission_model_glibc.md)
第四节与 [ABI 登记](abi_registry.md) 的分配流程。本文只冻结 M1 要实现的语义、线格式、错误优先级与验收；
未列能力一律不做，也不以符号存在或链接成功宣称 POSIX 权限完备。

范围：`utime/utimes/futimens/utimensat`、`chmod/fchmod`、`chown/fchown/lchown`、
`stat/fstat` 的 mode/时间投影、`access` 的 RDO 检查。不涉及所有权持久化、NSS、
ACL、xattr、symlink、atime/ctime 持久化、原生文件系统或 glibc 切换。

## 1. 现状盘点（实现即事实）

| 项 | 现状 | 位置 |
|---|---|---|
| 线路 | `request/response` 各 4096 字节；`abi_version = 2`；magic `FREQ/FRES` | `src/shared/include/xos/file_abi.hpp` |
| 版本协商 | 客户端发送 `version=2`，服务拒绝 `!= 2`；无逐 op 能力协商 | `src/user/sdk/file_client.cpp:48,59`；`src/user/services/files.cpp:1190` |
| op | 1–28 已分配（含 20–28 扩展）；下一个可用 29 | 同上 |
| 会话 | 内核认证 `pid/parent_pid`；最多 8 个会话；会话持有 cwd；无 uid/gid 字段 | `files.cpp` `client_session` |
| 句柄 | `open_record(handle, description)` + `open_description(object, flags, position)` + `file_object`（稳定身份 = 目录扇区/偏移/inode）；支持 unlink/anonymous | `files.cpp` |
| stat | 服务返回大小、目录位、unlink 位、inode；libc 合成 `mode=0777`、`uid=gid=0`、`nlink=1`、时间为 0 | `newlib_syscalls.cpp:365`；`file_abi.hpp` `stat_*` |
| access | FAT 上 uniform 放行；`X_OK` 只对 ELF 做 pin/校验，不检查模式位 | `newlib_syscalls.cpp:770` |
| 元数据写 | `utime/chmod/chown` 全部 `ENOSYS` | `newlib_syscalls.cpp:1929` |
| FatFs | `FF_USE_CHMOD=0`（`f_chmod/f_utime` 未编译）；`FF_FS_READONLY=0`；`f_utime` 只写 mtime（FILINFO `fdate/ftime`）；无 atime/ctime/uid/gid | `src/third_party/fatfs/ffconf.h:11,45`；`ff.c:5428,5482` |
| SDK | 普通与线程两个 profile 都编译同一 `libc/*.cpp` 并静态链接 `libxos.a`；文件服务是镜像内独立进程 | `scripts/user_build.py`；`scripts/build_threading_sdk.py` |
| 现存证据 | `/dev/null`、system/popen、控制台读；元数据无证据 | `docs/reports/*_2026111*/` |

## 2. 目标语义（M1）

挂载/后端 profile 公布一个默认投影：文件 `0644`、目录 `0755`（可执行位对目录表示可遍历），
`uid=gid=0`，`nlink=1`。投影不是安全凭据；`uid=0` 不授予任何额外 authority。

| 调用 | 允许 | 失败 |
|---|---|---|
| `stat/fstat` | 类型、大小、真实 mtime（FAT 2 秒量化）、RDO 投影后的 mode、inode | 对象不存在→`ENOENT`；fd 无效→`EBADF` |
| `chmod/fchmod` | 仅当请求 mode 与投影在“只读位”之外完全一致：`0644/0444`（文件）、`0755/0555`（目录，若目录 RDO 语义经实测成立）；据此设置/清除 `AM_RDO` | 不可表达（`0600`、`0777`、组/其他写、读/执行位差异）→`ENOTSUP`；`S_ISUID/S_ISGID/S_ISVTX`→`ENOTSUP`；只读卷→`EROFS` |
| `chown/fchown/lchown` | `uid/gid` 为 `-1` 或等于合成值 `0`：无变更，成功 | 要求改变为其它值→`ENOTSUP`；无更改但仍需做路径/fd 校验 |
| `utime/utimes/futimens/utimensat` | 设置 mtime；`UTIME_OMIT` 用于 atime；两个 OMIT 仍校验对象与参数 | 显式 atime 更新→`ENOTSUP`；`UTIME_NOW` 在无可用墙钟时→`ENOTSUP`（不得静默用 1970）；无效纳秒→`EINVAL`；只读卷→`EROFS` |
| `access` | `R_OK` 放行；`W_OK` 在 RDO 或只读卷时 `EACCES`；`X_OK` 对普通文件 `EACCES`（执行由 loader authority 决定，不由 mode 位） | 目录遍历仍按路径解析与 authority 判定 |

时间投影：`atime/ctime` 无可持久字段，`stat` 回读为 mtime；文档与测试必须明确这一点。
FAT 时间按 **UTC** 解释（与 `sys_clock_realtime` 一致），禁止按本地时区静默改写日期。
mtime 量化 2 秒；设置后回读允许 ±2 秒。

已打开句柄语义：POSIX profile 下，`chmod` 不撤销已打开句柄的读写能力；已 `unlink`/anonymous
对象没有稳定路径，元数据写返回 `ENOTSUP`，不回退到 backing 名字。

## 3. 线格式与版本协商

保持 `abi_version = 2` 不变（既有静态工具继续可用）。新增 **op 29 `set_metadata`**，
用 `request.data` 承载独立版本的元数据结构：

```c
struct metadata_request {   // 40 bytes, little-endian
    u16 version;            // 1
    u16 mask;               // bit0 RDO, bit1 MTIME, bit2 ATIME
    u16 attr;               // 0 或 AM_RDO(0x01)
    u16 reserved;           // 0
    i64 atime_sec, atime_nsec;
    i64 mtime_sec, mtime_nsec;
};
```

- 选择对象：`request.handle != 0` 按句柄；否则按 `request.name`（路径，`name_length > 0`）。
  两者同时给出、或都为空 → `invalid`。`request.length` 必须等于结构大小，`flags/offset` 保留为 0。
- `mask` 未定义位、`version != 1`、`reserved != 0`、纳秒越界 → `invalid`。
- 能力探测：旧服务对未知 op 返回 `invalid`；libc 将元数据调用映射为 `ENOTSUP`（而非 `EINVAL`），
  调用方可据此降级。新服务对旧客户端完全透明（旧客户端不会发送 op 29）。
- 不升 `abi_version`、不改 request/response 布局；若 M2 需要新字段，另立 v2 结构并保留本结构只读。

## 4. 权限与 authority

- 现状只有粗粒度：内核认证会话（`parent_pid` 链）+ 文件服务写路径；没有按对象的元数据权利。
- M1 的保守规则：元数据写要求与“写该对象”相同的粗粒度服务授权（认证会话、非维护锁定、
  非只读卷）；不引入 uid 检查，也不把 `chmod` 当作提权。无法可靠区分的操作（`chown`、
  不可表达 mode、显式 atime）一律 `ENOTSUP`，不静默成功。
- 更细的 metadata capability、撤销与在途操作边界属 M2；在此之前不得新增“uid 0 万能”或
  “路径即权限”的旁路。

## 5. FatFs 与后端

- M1 需把 `FF_USE_CHMOD` 置 1（`FF_FS_READONLY` 保持 0），重建文件服务；
  `f_chmod/f_utime` 仅接受路径，服务以对象存储路径执行，并对 unlinked/anonymous 拒绝。
- 目录 RDO：先实测 FatFs 与真实磁盘行为（`f_chmod` 后能否继续创建/删除子项）再决定是否
  承诺 `0555`；不成立的组合在 `chmod`/`stat` 上返回 `ENOTSUP`/按投影降级并记录。
- 只读介质/写保护：不得只改 `stat`；`chmod`/时间写与数据写都要经后端检查，映射 `EROFS`。
- 失败回滚：单字段 op 才允许“失败即无变更”；多字段请求必须先整体校验，若后端无法保证，
  只提交一个字段或改为多个 op，不宣称原子性。

## 6. 错误优先级（冻结）

1. 结构/版本/长度/保留位/纳秒非法 → `invalid`
2. 句柄无效 → `bad_handle`；路径不存在 → `not_found`
3. unlinked/anonymous 对象 → `ENOTSUP`
4. 不可表达请求（mode 位、显式 atime、chown 改值）→ `ENOTSUP`
5. 只读卷/写保护 → `EROFS`
6. 后端失败 → `io`/`no_space`（按现有映射）
7. 无 authority（M2 引入后）→ `EACCES`

先校验输入与其组合，再解析对象，再判支持性，最后落盘；任何一步失败都不得产生部分变更。

## 7. 兼容与回滚

| 组合 | 预期 |
|---|---|
| 新 libc + 新服务 | 全部语义 |
| 新 libc + 旧服务 | op 29 → `invalid` → libc `ENOTSUP`；`stat/access` 仍按旧合成值 |
| 旧 libc + 新服务 | 不发送 op 29；数据/路径语义不变 |
| 普通 SDK / 线程 SDK | 同一 `libc` 源码与线路，分别构建、分别验收 |

回滚：还原 `FF_USE_CHMOD`、服务 op29 与 libc 映射需同镜像回退；没有磁盘格式变化、没有
sidecar、没有新 syscall，回滚不影响既有文件内容。已发布的 SDK 不与新服务混跑（静态镜像）。

## 8. 验收（M1 必须以客体原生日志为准）

- `stat/fstat`：文件/目录投影、RDO 变化后的 mode 与 `access(W_OK)` 一致；`uid/gid=0`。
- `chmod`：`0644↔0444` 往返；`0600/0777/04755` → `ENOTSUP`；RDO 后 `open(O_WRONLY)`/`truncate`
  失败，清除后恢复；目录按实测结论验收。
- `chown`：`-1/0` 无变更成功；其它值 `ENOTSUP`。
- 时间：`utime`/`utimensat` 设置 mtime 回读（±2 秒）；显式 atime → `ENOTSUP`；双 `UTIME_OMIT`
  仍做参数校验；无墙钟时 `UTIME_NOW` → `ENOTSUP`。
- 对象生命周期：`unlink`/anonymous 后元数据写 → `ENOTSUP`；rename 后不作用到同名新对象。
- 只读卷：`chmod`/时间写/数据写都 `EROFS`，`stat` 仍可读。
- 兼容：用构造的“旧服务”响应验证新 libc 的 `ENOTSUP` 降级；旧 libc 对新服务无回归。
- 双 shell（xsh + dash）、双 SDK（single/threaded）；冻结输入、镜像、包与输出哈希。

## 9. M1 实施清单

1. 本契约合入 + `abi_registry` 占号 op29（claimed）。
2. `ffconf.h` 打开 `FF_USE_CHMOD`，重建文件服务；先做 RDO/mtime 探针测量目录与只读卷行为。
3. 服务实现 op29 + `metadata_request` 解码、错误优先级、unlinked 拒绝。
4. libc 映射 `utime/utimes/futimens/utimensat/chmod/fchmod/chown`，并让 `stat/access` 使用
   投影与 RDO；保持旧服务降级为 `ENOTSUP`。
5. 上述验收全绿后再更新 `docs/ports_ledger.md` `PL-0005` 与 #123 状态；不得提前标 fixed。

## 10. 非目标

所有权/组/NSS/`set*id`、mode/umask 持久化、ACL、xattr、symlink、atime/ctime 持久化、
原生文件系统、sidecar、glibc sysdeps、`chmod` 影响已打开句柄、目录原子 rename 事务。
