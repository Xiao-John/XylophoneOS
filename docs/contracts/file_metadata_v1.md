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

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:cbe96fa6c974340dc570f21e937fbf5d6813583e6fa7eefc27752c3ec6aa3479 -->

## 2. 目标语义（M1）

挂载/后端 profile 公布一个默认投影：文件 `0644`、目录 `0755`（可执行位对目录表示可遍历），
`uid=gid=0`，`nlink=1`。投影不是安全凭据；`uid=0` 不授予任何额外 authority。

| 调用 | 允许 | 失败 |
|---|---|---|
| `stat/fstat` | 类型、大小、真实 mtime（FAT 2 秒量化）、RDO 投影后的 mode、inode | 对象不存在→`ENOENT`；fd 无效→`EBADF` |
| `chmod/fchmod` | 仅当请求 mode 与投影在“只读位”之外完全一致：`0644/0444`（文件）、`0755/0555`（目录，若目录 RDO 语义经实测成立）；据此设置/清除 `AM_RDO` | 不可表达（`0600`、`0777`、组/其他写、读/执行位差异）→`ENOTSUP`；`S_ISUID/S_ISGID/S_ISVTX`→`ENOTSUP`；只读卷→`EROFS` |
| `chown/fchown/lchown` | `uid/gid` 为 `-1` 或等于合成值 `0`：无变更，成功 | 要求改变为其它值→`ENOTSUP`；无更改但仍需做路径/fd 校验 |
| `utime/utimes/futimens/utimensat` | 设置 mtime；`UTIME_OMIT` 用于 atime；两个 OMIT 仍校验对象与参数 | 显式 atime 更新→`ENOTSUP`；`UTIME_NOW` 在无可用墙钟时→`ENOTSUP`（不得静默用 1970）；无效纳秒或 mtime 超出 FAT 范围→`EINVAL`（线路 `invalid`）；只读卷→`EROFS` |
| `access` | `R_OK` 放行；`W_OK` 在 RDO 或只读卷时 `EACCES`；`X_OK` 对普通文件 `EACCES`（执行由 loader authority 决定，不由 mode 位） | 目录遍历仍按路径解析与 authority 判定 |

时间投影：`atime/ctime` 无可持久字段，`stat` 回读为 mtime；文档与测试必须明确这一点。
FAT 时间按 **UTC** 解释（与 `sys_clock_realtime` 一致），禁止按本地时区静默改写日期。

FAT 可表达年份为 **UTC 1980 至 2107 年**，可存储的 mtime 最小值为
`1980-01-01T00:00:00Z`，最大值为 `2107-12-31T23:59:58Z`（均含边界）。
mtime 量化 2 秒；设置后回读允许 ±2 秒。实际待设置的时间（含 NOW 解析结果）须在
上述闭区间内，先检查秒与纳秒组成的完整值，再量化；超出范围返回线路 `invalid`，libc
按现有 `error_from_file` 映射为 `EINVAL`，不截断、钳位或回绕。OMIT 不作为待设置时间检查。

已打开句柄语义：POSIX profile 下，`chmod` 不撤销已打开句柄的读写能力；已 `unlink`/anonymous
对象没有稳定路径，元数据写返回 `ENOTSUP`，不回退到 backing 名字。

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:badab67e47cf46f7cac27c853495bf866d1ec73bfe5f3df214d38c68c89349bd -->

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

### stat/fstat 读取扩展（M1）

成功响应保留 `value`（大小）、`flags`（目录/unlinked）与 `reserved`（inode）的既有含义。
在 `response.data` 从偏移 0 编码以下 **24 字节**记录，`response.length = 24`；
多字节整数均为 little-endian，字段无填充，偏移相对 `response.data`：

| 偏移 | 类型/字节数 | 含义 |
|---|---|---|
| 0 | 4 字节 | 显式标识 ASCII `FMET`（`46 4d 45 54`） |
| 4 | u16 | 读取格式版本 `1`（独立于 ABI 与写请求版本） |
| 6 | u16 | 记录长度 `24` |
| 8 | i64 | `mtime_sec`，Unix epoch 起的 UTC 秒，二进制补码 |
| 16 | u32 | `mtime_nsec`，FAT 回读为 `0` |
| 20 | u32 | `mode`，类型位与 RDO 投影后权限位；采用 libc `S_IFREG/S_IFDIR` 及八进制权限位编码 |

新 libc 先验证成功响应及长度边界；`length = 0` 表示旧服务（现有服务将响应清零，
stat/fstat 不写 data），使用既有合成值：权限 `0777`、`uid=gid=0`、`nlink=1`、
`atime=mtime=ctime=0`，类型/大小/inode 仍取既有字段；access 沿用旧服务行为。
非空记录必须匹配 `FMET`、版本 `1`、记录长度及响应长度 `24`，纳秒和类型位也须合法，
否则按无效服务响应报 `EIO`，不降级。有效记录的 mtime 即使为零也按新格式读取；
不能以时间零值探测能力。新格式的 `atime/ctime` 按第 2 节投影，uid/gid/nlink 仍合成。
旧 libc 忽略新增 data，继续读取原有字段。上述扩展不改变 ABI v2 外层布局或 op 29 写请求。

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:bb5f00e8d013d43cba348c9f2244d530a7e6d2dd0dbd29da1f3ee00944df0f90 -->

## 4. 权限与 authority

- 现状只有粗粒度：内核认证会话（`parent_pid` 链）+ 文件服务写路径；没有按对象的元数据权利。
- M1 的保守规则：元数据写要求与“写该对象”相同的粗粒度服务授权（认证会话、非维护锁定、
  非只读卷）；不引入 uid 检查，也不把 `chmod` 当作提权。
  `chown` 的 uid、gid 各自为 `-1`（不修改）或 `0` 时，校验对象后无变更成功；
  仅当需要修改的 uid 或 gid 为其他值时返回 `ENOTSUP`。
  不可表达 mode、显式 atime 仍一律 `ENOTSUP`。

- 更细的 metadata capability、撤销与在途操作边界属 M2；在此之前不得新增“uid 0 万能”或
  “路径即权限”的旁路。

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:bbb6c1923446e242ce60880b94b3d26c27e8d256d5e46bf1d9de93288afd2678 -->

## 5. FatFs 与后端

- M1 需把 `FF_USE_CHMOD` 置 1（`FF_FS_READONLY` 保持 0），重建文件服务；
  `f_chmod/f_utime` 仅接受路径，服务以对象存储路径执行，并对 unlinked/anonymous 拒绝。
- 目录 RDO：先实测 FatFs 与真实磁盘行为（`f_chmod` 后能否继续创建/删除子项）再决定是否
  承诺 `0555`；不成立的组合在 `chmod`/`stat` 上返回 `ENOTSUP`/按投影降级并记录。
- 只读介质/写保护：不得只改 `stat`；`chmod`/时间写与数据写都要经后端检查，映射 `EROFS`。

- 失败回滚：本契约所有 op 请求失败时均不得产生部分变更，单字段也不例外。
  同时通过 mask 携带 RDO 与 MTIME 的请求必须在任何写入前整体校验输入、对象、支持性、
  授权与介质约束，并作为一个请求原子提交，不得只提交一个字段或拆成多个 op。
  若后端不能保证失败无变更，须在写入前返回 `ENOTSUP`。现有依次调用
  `f_chmod`/`f_utime`（各自 sync）的方式不构成原子提交；M1 在提供可验证的提交机制前
  必须拒绝该组合。任何将来开放的机制须先记录其提交点、失败恢复、并发可见性以及
  服务崩溃/断电的保证范围，并以故障注入验证；不能以单线程或尽力回滚代替证明。

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:739c0573e3b8b3fdc12fbac0540d29a0c62b8571264f1ec0de42f0ebfc599790 -->

## 6. 错误优先级（冻结）

1. 结构/版本/长度/保留位/纳秒非法，或待设置 mtime 超出第 2 节 FAT 范围 → `invalid`（libc `EINVAL`；沿用现有映射）

2. 句柄无效 → `bad_handle`；路径不存在 → `not_found`
3. unlinked/anonymous 对象 → `ENOTSUP`

4. 不可表达请求（mode 位、显式 atime、chown 改值），或后端不能保证失败无变更（含 RDO + MTIME 组合）→ `ENOTSUP`

5. 只读卷/写保护 → `EROFS`
6. 后端失败 → `io`/`no_space`（按现有映射）
7. 无 authority（M2 引入后）→ `EACCES`

先校验输入与其组合，再解析对象，再判支持性，最后落盘；任何一步失败都不得产生部分变更。

<!-- /coderabbit-ai-generated:v1 -->

## 7. 兼容与回滚

| 组合 | 预期 |
|---|---|
| 新 libc + 新服务 | 全部语义 |
| 新 libc + 旧服务 | op 29 → `invalid` → libc `ENOTSUP`；`stat/access` 仍按旧合成值 |
| 旧 libc + 新服务 | 不发送 op 29；数据/路径语义不变 |
| 普通 SDK / 线程 SDK | 同一 `libc` 源码与线路，分别构建、分别验收 |

回滚：还原 `FF_USE_CHMOD`、服务 op29 与 libc 映射需同镜像回退；没有磁盘格式变化、没有
sidecar、没有新 syscall，回滚不影响既有文件内容。已发布的 SDK 不与新服务混跑（静态镜像）。

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:f2fa56a451230158e606d7df7a64a7c7b6b38b1b666a7b300e8f2a05a65dadc1 -->

## 8. 验收（M1 必须以客体原生日志为准）

- `stat/fstat`：文件/目录投影、RDO 变化后的 mode 与 `access(W_OK)` 一致；`uid/gid=0`。
- `chmod`：`0644↔0444` 往返；`0600/0777/04755` → `ENOTSUP`；RDO 后 `open(O_WRONLY)`/`truncate`
  失败，清除后恢复；目录按实测结论验收。

- `chown`：uid/gid 各自取 `-1/0` 的全部组合均校验对象并无变更成功；无效 fd/路径仍报错；任一待改值为其它值 → `ENOTSUP`。

- 时间：`utime`/`utimensat` 设置 mtime 回读（±2 秒）；显式 atime → `ENOTSUP`；双 `UTIME_OMIT`
  仍做参数校验；无墙钟时 `UTIME_NOW` → `ENOTSUP`。
  UTC 最小值 `1980-01-01T00:00:00Z` 与最大值 `2107-12-31T23:59:58Z` 均可设置并准确回读；
  下界前/上界后（含纳秒越界边界）的时间 → `invalid`/`EINVAL`，mtime 与 RDO 均不改变。
- 原子性：单字段及 RDO + MTIME 请求均覆盖校验失败、只读介质和后端故障，失败后回读所有
  字段不变；组合请求若不受支持，验证写入前 `ENOTSUP`，不得以拆分请求通过验收。
  开放原子提交时须额外按所声明的崩溃/断电保证范围注入故障并验证恢复。

- 对象生命周期：`unlink`/anonymous 后元数据写 → `ENOTSUP`；rename 后不作用到同名新对象。
- 只读卷：`chmod`/时间写/数据写都 `EROFS`，`stat` 仍可读。

- 兼容：构造旧服务 `stat/fstat length=0` 响应验证旧合成值及 op29 `ENOTSUP` 降级；
  构造有效 `FMET` v1 的零值 mtime 响应，确认不会被误判为旧格式；截断、错误标识/版本/长度
  的非空响应须报 `EIO`；分别验证 stat/fstat 的字段、字节序与 RDO mode；旧 libc 对新服务无回归。

- 双 shell（xsh + dash）、双 SDK（single/threaded）；冻结输入、镜像、包与输出哈希。

<!-- /coderabbit-ai-generated:v1 -->

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
