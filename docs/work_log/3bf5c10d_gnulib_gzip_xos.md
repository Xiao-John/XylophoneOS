# 3bf5c10d Issue 133：真实 GNU gzip 与共享 gnulib XOS/glibc 后端闭环

2026-11-28。基线 `344655c3f2279a10c62fce5ea039c741aa6172f1`，独立分支
`codex/issue-133-gnulib-20261128`。本组修复 Issue #133 对应的真实移植问题，
不通过仅改 Issue 状态、zlib 替代程序或文档声明完成闭环。

## 范围、实现与选择

默认 SDK 已切换 glibc。旧 Issue 所列程序名、宽类型、`fdopendir` 和 `lstat`
缺口在这一轨有真实实现；消费者使用实际生成的 gnulib 头/库确认这些行为。
没有把 newlib 私有头、`_reent` 或旧类型布局带入新的公共接口。

仍然存在的 FD 限制查询由 `src/ports/glibc/sysdeps/xos/getrlimit.c` 和
上游实际选择的 `getdtsz.c` 修复。新增私有 `xos_file_limits.h` 与
`xos_file_runtime.c` 共用容量 32；不改变 FD 表大小、协议或任何 syscall。
files、console、terminal、pipe、socket 都使用这一表；文件服务的 16 handle
独立配额没有提高。`getrlimit64` 使用上游转接。`setrlimit`、其他资源限额
及 `sysconf` 的未实现能力没有冒称支持。契约更新 `glibc_files_v1.md`；
共性缺口登记 PL-0018。

`scripts/gnulib_xos.py` 是可复用配置入口，绑定单一 SDK 的工具、头、CRT 和库，
清理继承的缓存/编译环境，并从 SDK stub 清单生成负向 Autoconf 答案。显式
处理 `libc_sigaction` 公共拼写和没有 linker stub warning 的 `sigprocmask`。
`src/ports/gnulib/` 保存真实 XOS target 识别及无信号 backend 补丁；不把 XOS
当成 Linux、不批量断言 gnulib 特性已实现。

实际配置暴露 gnulib 的假设：缺少 `sigaction` 就缺少类型，且可用 Windows
信号仿真。XOS glibc 已有类型却没有信号送达。新补丁保留真实 glibc 类型与
信号集运算，送达/屏蔽返回 `ENOTSUP`、错误时不改输出。gzip 的私有信号
保护步骤单独关闭，避免读取失败 `sigaction` 的未初始化结果。文件失败依然
进入上游清理与真实退出码。

`src/ports/gzip/` 与 `scripts/build_gnu_gzip.py` 处理 signed GNU gzip 1.14。
官方原包、分离签名、GNU keyring 提取的 Jim Meyering 公钥与 COPYING 均锁定；
构建先验签不可变快照再解包，保存配置/工具/SDK/源码身份。原始声明保留，
`licenses/components.json` 与 `docs/licensing.md` 登记材料及本地修改。

glibc 尚无文件元数据写操作，本组不暗中扩大到该专项：gzip 使用上游
`NO_UTIME`，不恢复文件系统时间戳；完整路径回退避免假装支持 dirfd 相对路径；
权限投影相等才视为已经达到效果，无法表示的变更真实失败、保留输入并清理输出。
`--help` 和配方 README 明示限制。没有发布或改绑旧 SDK 二进制资产。

## 实际构建与运行

均在已发布 glibc SDK 的 Linux 开发环境执行。工作区独立可写，原 SDK 只读。
工具为 GCC 16.2.0、Binutils 2.47.20260726、GNU Make 4.4.1、gpgv 2.2.40、
QEMU 11.1.3。命令中的环境变量表示调用者选定的认证缓存/基线构建位置：

```sh
python3 scripts/build_glibc_sdk.py \
  --archive "$XOS_SOURCE_CACHE/glibc-2.44.tar.xz" \
  --output build/issue133_sdk_v2 --jobs 2
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build build/issue133_sdk_v2 --id xos-x86_64-glibc-issue133 \
  --feature directories --feature stdio_transfer --output build/issue133_profile.json
python3 scripts/build_gnu_gzip.py \
  --archive build/issue133_downloads/gzip-1.14.tar.xz \
  --sdk build/issue133_sdk_v2 --profile build/issue133_profile.json \
  --output-dir build/issue133_gzip_v3 --jobs 2
python3 scripts/build_dash.py --sdk build/issue133_sdk_v2/sysroot \
  --glibc-profile build/issue133_profile.json --receipt build/issue133_dash.json
python3 tests/gnu_gzip_guest.py --system-build "$XOS_BASELINE_SYSTEM_BUILD" \
  --gzip-build build/issue133_gzip_v3 --dash-receipt build/issue133_dash.json \
  --output build/issue133_guest_v2
python3 scripts/build.py --output-dir build/issue133_license --quiet-demos-on-launch
python3 scripts/license_audit.py --build build/issue133_license
```

glibc SDK `static_sdk_built`，1098 个产物；manifest SHA
`7b3d51c8e13c9b0435a8bdfcbe8b3adff22540e426be43741e19dfc94b56e14e`。
GNU gzip ELF SHA
`2b2f22a4f351b7ef574917eb3824f6f4589d716d6deba56cf8235c45183e09ce`；
消费者 SHA `58958733781e0aa8b00ddb620ff05fcabab3ae6b0b791a22286f03053f2bfece`。
原样 baseline OS `7e9d4063fa8154b7` 与独立 glibc SDK 分别绑定；新系统材料
构建 `df4757640f8b7ec2` 只用于许可证 SDK 副本检查，未用于客体结论。

运行器检查原始构建输入、实际 ISO/程序字节、baseline kernel/native-service
源码、runner 及依赖、QEMU/离线磁盘工具/host gzip 身份。QEMU 退出并释放镜像
后才做离线读取，结束时再次核对工具/程序未变。公开证据为
[gnulib_gzip_20261128](../reports/gnulib_gzip_20261128/README.md)：一个最小化
派生回执及两个原字节日志，平铺根清单覆盖，原始来源哈希保留。

## 通过、失败、未运行

**最终通过：**13 个顶层客体 case；真实 gnulib 程序名/宽类型/flags/目录与
错误所有权/32 FD 耗尽/rlimit64/无信号边界；GNU gzip 普通文件压缩/解压、
`-k` 保留与正常删除、CRC/截断/非格式/缺失输入；dash stdin/重定向/管道；
host GNU gzip 与 XOS 双向互操作，二进制样本 8496 字节；拼接 members。
真正的已关闭 stdout 写失败为 EBADF/exit 1；碰撞为 exit 2，原输入及已有输出
不变；默认 `-d` 的坏 CRC 不删除输入且清除部分输出。缺失父目录的重定向是
独立 shell 错误。每个 case 资源恢复到 `129693/3/1`，用户文件不变。

**构建拒绝门通过：**同大小篡改原包被 source lock 拒绝；原发布 SDK 因仍缺
native 查询前提被拒绝，未开始 configure。GNU 原包则真实验签通过。
**许可门通过：**10 份材料与 SDK 副本校验，登记的 open 项为 0；原有逐成员和
二进制分发限制保留，不把材料检查提升为分发许可。

**公开交付门：**`check_public_evidence_paths.py --index --base origin/main`
实扫暂存 28 个文件，`PUBLIC_READY`、无 findings；`verify_evidence_index.py`
检查本目录 4/4 叶子通过；`git diff --cached --check` 通过。仅本次三个 GNU
patch 的必要上下文空白及原始串口 CRLF/prompt 按精确路径在 `.gitattributes`
保留。全局 `report_manifest_check.py` 另有 17 条既有 glibc_v2/mobius 清单
错误；逐一比对受影响 manifest 与 origin/main 原字节一致，本目录列 compliant。
原始输出保存在 `build/issue133_public_paths.log` 和
`build/issue133_report_manifest.log`，派生回执列明既有失败范围，未修改冻结旧证据。

**开发期失败：**首 SDK 因错用 GNU selector 名及空指针拼写而主动中断，随后
在新目录完整重建；首 gnulib 构建遇信号类型/Windows 假设冲突；消费者曾包含
本快照不存在的 `stat-macros.h`，现使用生成 `sys/stat.h`；第一轮 guest 脚本
误用受限 `exec-file` 使 dash 子进程收到 EPERM，按已存在的普通启动契约修正
后全套重跑。旧 stock gzip 的 named 操作卡住已被最终实际 named 用例覆盖。
这些失败均保留原始 build 记录，不把未完成尝试算成成功。

**未运行/未实现：**全上游 `make check`、其他 GNU 包和全部 gnulib 模块、legacy
newlib 回填、异步信号、任意 Unix 模式/所有权、文件系统时间戳恢复、完整二进制
分发及新 prerelease。无需更改 `docs/state.md`；按约定由合并者维护全局快照。

## 后续交接

发布独立 PR，审查范围为 Issue #133 的实际默认 glibc 后端与 GNU gzip 回归。
其他 GNU 工具应复用本配置，针对各自模块增加真实消费者与失败用例；不能把本次
gzip 通过当成 coreutils/tar/sed/grep/findutils 全部移植完成。若改动 SDK、配方
或配置输入，要新建输出重建并重验，不能改旧回执哈希为新资格。正式分发 GNU
gzip 时须交付匹配的上游源、补丁、配方和 GNU/SDK 许可材料。
