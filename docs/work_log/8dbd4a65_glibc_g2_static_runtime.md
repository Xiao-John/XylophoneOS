# glibc G2：隔离静态 SDK、原生 CRT 与主线程 TLS

## 目标与边界

本模块接续 glibc G1，使用 `xos-glibc-sdk-preview` release 的 GNU/Linux
工具环境，完成独立 glibc 静态库和真实 C 程序启动链。通用当前线程 FS 安装已按
[线程契约](../contracts/threading.md) 和
[ABI 注册表](../contracts/abi_registry.md) 先登记；内核不解释 glibc TCB。
G3 的线程 API 增强与文件服务后端分别提交，G2 默认仍是内核标准句柄控制台 I/O。

当前 glibc 2.44 源归档 SHA-256 为
`37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`。
其独立签名信任核验仍是 `source_lock.json` 记录的 NOT_RUN，产物用于研究。
preview 工具为 GCC 16.2.0、Binutils 2.47.20260726、GNU make 4.4.1、NASM 3.02；
客体使用 preview QEMU 11.1.3，区别于仓库 QEMU 11.1.2 锁，本模块记录该验证例外。

## 实现

- 构建脚本逐个应用编号补丁、覆盖 XOS sysdeps，使用独立空 sysroot 和当前宿主
  triplet。完整静态 libc/libm 采用真实源码构建；补足静态配置生成头、上游 generic
  源文件缺少的声明、NPTL 所需对象、errno 地址函数及 CPU tunables 对象。
- 自有 CRT 验证 XOS 启动结构、argv/envp 边界、扩展 flags/保留值和支持能力；
  依据实际映射 ELF 构造 libc 私有 auxv，获取原生熵，调用真正的
  `__libc_start_main`。glibc 分配真实 TCB/static TLS，并用 sys35 current-thread
  mode 安装 FS。libc 内部初始化后、应用 constructor 前建立 errno 初始值。
- 标准库使用原生堆与 VM 支持，控制台 read/write/close 经过明确错误转换；
  getpagesize 返回公开 ABI 的 4096。未支持 fork、POSIX timer 等接口明确失败。
- 正常 exit 在 libc 清理锁之前检查线程存活计数；活跃 peer 仍存在时 raw 输出诊断
  并退出 127。已清理 peer 的计数以 release 发布，exit 用 acquire 读取，再跨越
  原生终止屏障运行全局清理。工作线程持有 FILE/malloc 锁时的完整正常退出语义
  仍待实现，当前采用有界失败。
- SDK 安装真实 archive/header/CRT/linker script；stubs.h 从已安装静态库的
  `.gnu.glibc-stub.*` 节生成。保存 glibc/GCC runtime 许可、完整 port、补丁索引、
  构建脚本、编译器私有头和 libgcc/CRT 来源散列。构建末尾再次验证源集合、
  归档与工具散列，输入变化即失败。
- 公共链接 helper 校验 SDK manifest 和产物散列，只显式链接该 SDK 的对象/库，
  检查 x86-64 静态 ET_EXEC 与无 W+X 装载段。preview 裸机 GCC 在 builtin 模式
  删除了 malloc/errno 与 aligned_alloc 探针调用，反汇编已确认，因此 helper
  默认 `-fno-builtin`；负向 malloc 探针另用 volatile 函数指针保存实际调用。

构建/链接用法与范围见 [port README](../../src/ports/glibc/README.md)。
独立 G3 文件 backend 的基础公开 flags/stat 头已纳入 G2 编译基础，安装头保持
自包含，避免 sysdeps 的 include_next 链在安装后消失。

## 验证进展

### 已运行

- preview SDK 环境内，开发候选完整 `make lib`、`install-headers`、`install-lib`
  成功；静态 libc.a 约 21 MiB。该候选曾用于组合诊断，正式 G2 会另从纯 G2 源
  快照全新构建，正式结果单独补录。
- `tests/fixtures/glibc_g2/static_main.c` 已在包含通用 TLS 扩展的新系统中实际
  运行：`alpha` 返回 37，`alpha exit` 返回 39；两次均通过 constructor、已初始化
  与零值 TLS、errno 隔离、argv/PATH、auxv、getpid、错误转换、五组
  malloc/realloc/free、calloc/aligned_alloc、SIZE_MAX+ENOMEM、setjmp/longjmp、
  printf、缓冲输出、atexit 逆序和 destructor 检查，并恢复资源基线。
  这是开发候选的诊断结果；对应程序构建为 `diagnostic_linked`，没有提升为正式
  source-bound SDK 验收。
- 真实客体定位并修复了 libc 早期可选探针污染 constructor errno 的问题。
  诊断明确观察到正确初始 TLS `123456789abcdeff`、零值 TLS 和 constructor
  修改后的 `123456789abcdea5`，随后补齐应用进入前 errno 状态。
- 纯 G2 全新构建发现 generic fstatat/fstatat64 被先前诊断 overlay 遮蔽的缺失
  include，以及 open/open64 缺少可变参数声明，均已修正。纯 G2 源 `make lib`
  已通过；继续执行新目录 manifest 与客体闭环。
- 控制台单次写限制为 256 字节。G2 wrapper 现返回合法短写，由 stdio 连续写完，
  且区分内核 pipe 的原子写与事件等待；debug serial 空读通过计时等待避免忙转。
  fixture 增加公开已安装 fcntl/stat/param 头、getpagesize 保留 errno、零长度 I/O
  和 512 字节 fwrite/fflush。fatal 输出也按 256 字节分段，保持无需 libc 锁。
- G3-T 的新目录构建实际暴露 SDK 安装竞态：同一并行 make 同时运行
  install-headers/install-lib，两个递归依赖图竞争 errno.o.T 与 Versions.mk，
  导致临时文件缺失/内容被覆盖。构建脚本改为完整并行构建后，分别串行执行两个
  安装阶段。该失败日志 SHA-256 为
  `a37b3ed786262a46a3166be901452ec963cfb632d55ba21d19d8b0c873853076`；
  修复后重新构建并绑定正式验收，避免仅依赖未触发竞争的一次成功。

- 再次并行新构建定位到上游 Makeconfig 的生成顺序缺边：gcc-macros.h.in
  recipe 强制 include libc-modules.h，却只声明 config.status 依赖。0018 现明确
  依赖 libc-modules.h、config.h 和 libc-symbols.h；其余传递 include 是固定源码
  头，未引入 before-compile 的自依赖环，完整库仍并行构建。

### 最终 source-bound 验收

测试代码来源为提交 `0b28799c04d32158952712ca3250db7d1d255645`。
在该纯 G2 快照上从新目录构建 SDK 和系统，未复制 G3 file/thread overlay。
完整 `make lib`、顺序 `install-headers`/`install-lib`、CRT 编译及 SDK 材料安装
全部通过；manifest 为 `static_sdk_built`，绑定 649 个 SDK 文件和 315 个实际
stub 标记。SDK 的构建结果与后续客体报告分别保存，客体 runner 验证完整源集合、
所有 SDK/system artifact 散列及测试前后输入稳定性。

以下命令在 preview SDK GNU/Linux 工具环境执行；`XOS_GLIBC_ARCHIVE` 指向上述
已核对 SHA-256 的源归档：

```sh
python3 scripts/build_glibc_sdk.py \
  --archive "${XOS_GLIBC_ARCHIVE}" --output build/g2_static_verified --jobs 8
python3 scripts/build.py --output-dir build/g2_system_verified
python3 tests/glibc_static_guest.py \
  --system-build build/g2_system_verified --glibc-build build/g2_static_verified \
  --output build/g2_guest_verified --suite g2 --repetitions 3
python3 tests/tls_current_guest.py \
  --system-build build/g2_system_verified --output build/g2_tls_verified
```

- **G2 公共 API：PASS，6/6。** 三轮 return 37 与三轮 exit 39，均通过主线程
  TLS/errno、constructor、argv/PATH、真实 malloc/calloc/realloc/aligned_alloc、
  SIZE_MAX+ENOMEM、setjmp/longjmp、512 字节 stdio 分段、fflush、全缓冲退出、
  atexit 逆序和 destructor。每次精确恢复 `[129720, 3, 1]` 资源基线。
  两个普通 ELF 都没有 exec receiver 标记。
- **newlib 同系统对照：PASS。** 当前镜像中的 malloc/printf/exit 与资源回收通过。
- **通用 TLS：PASS，3/3 launch。** 每次覆盖 8 个无效地址、身份/旧模式/无效模式、
  两线程 160 次 yield 与抢占隔离、leaving 状态及资源恢复。
- `tests/glibc_g1_probe_test.py`：PASS；`tests/docs_consistency.py`：PASS
  （1036 个本地链接、78 个已分配 syscall、73 个历史来源）；
  `tests/abi_doc_consistency.py`：PASS。公共路径检查为 PUBLIC_READY，
  `git diff --check origin/main...HEAD` 通过。

系统 build_id 为 `b3cf48277c69f7bf`，QEMU 实际版本为
`11.1.3 (Debian 1:11.1.3+ds-2)`，使用 TCG 和串口；该环境禁止 AF_UNIX QMP
socket，runner 使用 `qmp_enabled=False`，串口验收完整执行。

| 产物或证据 | SHA-256 |
| --- | --- |
| `build/g2_static_verified/manifest.json` | `c4d9deecac7fa55024c244e821b25345b6980233b014c06bf4bf6cd6b92f762a` |
| `sysroot/usr/lib/libc.a` | `ceefe70eb0b2b7b71b92b90568c77d9133df10b6299a428d14a999f172caf1bb` |
| `sysroot/usr/lib/libm.a` | `ab7e095ebd75c65d138dd9d1250c90a413d790a002e58c7a0d813183ba8606b1` |
| `sysroot/usr/lib/xos_start.o` | `11de16d30a7fea271763c78df35058716f3998cbb892642964db72bd33bd2b8b` |
| `sysroot/usr/lib/xos_start_c.o` | `6795ede1a32d05a408f37d0072c09d87cdcfe08117283a76bd60672d5cdca435` |
| `sysroot/user.ld` | `f2a1263320fc08b0b1ba88d33f35b8886543244c9d5eb28eb532977144d4c611` |
| `build/g2_system_verified/manifest.json` | `a613166260d43850715555d0c460cafdabbf8172fb007718ca0e0a2dbf72c091` |
| `build/g2_system_verified/xos-install.iso` | `96a075da7082bcb6f39c401bf5466e788f8779b9be65a5a1f67809d12dfec847` |
| G2 return/exit ELF（字节一致） | `7a3765f7a790d9dfb6938287a72bd6d46febcc11017e7f69bcbc2e24c3903641` |
| `build/g2_guest_verified/report.json` | `72094b44c0328f907c5f097912024a84a317fc852fc253b79eb35ca1f035225b` |
| `build/g2_guest_verified/serial.log` | `d72388f7db93c215121d8cfa4dfe3756b460d4d89f9cce9b88feda7d9d403ff5` |
| `build/g2_tls_verified/report.json` | `e6eefc27a8fac47d4eca0974744fbaa4feabe7abb5b18f96ddad4ed61cad2e85` |
| `build/g2_tls_verified/serial.log` | `6c8cde7390e6b64ba233a019d226a905d577cf4786307cad6b066af2f45ccce9` |

### NOT_RUN 与后续模块

- G3 thread/file 专属客体及 active-worker fail-fast/last-worker 清理回归归属各自
  模块；G2 最终 runner 使用 `--suite g2`。
- 完整上游 glibc 测试套件、真实硬件、其他架构/固件、交互式非零 stdin、动态
  加载、libc 工具程序、C++ SDK、resolver/DNS 与广泛 POSIX 一致性尚未验收。
- 源归档签名的独立信任核验仍为 NOT_RUN。当前保留的是研究 SDK 和完整重建材料，
  发行许可/替换重链接方案及正式 SDK target 身份需独立收口。

## 实施中发现的缺口

默认 libc 保持独立。应用仍需隔离 SDK 和显式链接 helper；原生 toolchain 尚未
作为正式 XOS glibc target 发布。活跃 worker 的正常 exit、glibc 发起 fork/exec、
terminal handoff 和路径重开式 spawn redirection 是具体实现缺口。
构建所用早期开发目录的 manifest 保留失败与 diagnostic 状态，最终验收使用上表
`verified` 新目录的完整 source-bound 结果。下一步可在本提交基础分别叠加 G3-T
或 G3-F，重新构建对应 SDK/system，并运行统一 runner 的对应 suite；后续 source
变化必须重新绑定，不能复用上表的成功状态。
