# glibc G1：XOS 目标识别与配置阻塞调查

2026-11-13；基线 `ffc4ea69`，独立工作树；**G1 partial，XOS glibc 未构建、未运行**。补充动态链接目标见 [移植勘查](../plans/glibc_port_scout.md#动态链接明确目标与独立验收)。本次不修改公共 ABI、内核、SDK 或默认 libc。

## 输入与边界

沿用 [G0](../plans/glibc_g0.md) 的 glibc 2.44 候选归档，SHA-256 `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`；签名与可信发布者仍 **NOT_RUN**，仅用于研究，不可发行。`0001-config-sub-xos.patch` SHA-256 `5814d4d9f34271abc0aadccb29e9fe05589f16a257452df2ac3472659c95b2a4` 仅使上游 config.sub 识别 `x86_64-unknown-xos`；不是 sysdeps、ABI 或功能实现，不将其加入声称已验证的发行锁。

宿主 macOS arm64；目标编译器 `x86_64-elf-gcc 16.2.0` 的真实 `-dumpmachine` 为 `x86_64-elf`，不是 XOS 目标工具链。隔离下载并解包 GNU Make 4.4.1、Gawk 5.4.1、Bison 3.8.2，不升级共享依赖；Gawk 的私有副本重定位到本机依赖后重新签名。GNU readelf 使用对应 x86_64-elf 工具。`makeinfo` 与 GNU sed 未满足，配置警告部分特性/测试禁用。以上只消除调查中的工具障碍，不构成可发行、可复现供应链资格。

## 实测

1. 候选补丁后 `config.sub x86_64-unknown-xos` 输出该规范三元组。以脚本 `python3 scripts/glibc_g1_probe.py --archive "$GLIBC_ARCHIVE" --output "$NEW_SCRATCH"` 重放，归档哈希核对、私有解包和补丁应用成功；正常 configure 退出 1，报 `The GNU C library is currently unavailable for this platform`。
2. 相同脚本加 `--hacker-mode` 仅用于调查，绕过上游平台门；满足关键工具检查并明确选择目标 C/C++ 编译器后，在 sysdeps 搜索报 `Operating system xos is not supported`，退出 1。日志 SHA-256 `298810b17d56dbc411569853a446ac8b695115af6407079a395c3c8882433436`。该日志的路径和工具环境为本机临时数据，不是可移植复现命令或发布材料。
3. 为确认搜索行为，仅在丢弃型诊断源码副本创建**空** `sysdeps/xos`，并使用 hacker-mode；configure 退出 0，实际选择 `sysdeps/xos`、x86_64 通用目录和 `sysdeps/generic`。空目录没有提供任何 XOS 操作系统功能，**不能解释为 XOS 平台配置成功**。随后运行 GNU make，退出 2：`This configuration not matched in ../abi-tags`。不得随意给 XOS 伪造 GNU ABI tag 来宣称成功。生成配置还显示 C++ 编译器未通过链接检查；裸 `x86_64-elf` 和 XOS sysroot 的差异仍需解决。
4. 首次使用新工具时 configure 优先拾取系统旧 `gnumake`；通过私有 PATH 别名改正。补充 target readelf 和显式 CXX，避免宿主工具误选；辅助 makeinfo/sed 仍有警告。所有失败保留为失败，未执行静态 libc 交叉构建、目标头/符号资格、客体运行、动态链接、许可或源签名验证。

## 下一步

明确 XOS target 三元组及 GCC/binutils/sysroot 的真实匹配；依据上游端口方式设计 XOS sysdeps 的必要实现、启动及 ABI tag 策略和最早可执行纵切片。先盘点 generic ENOSYS/伪成功、构建需要的目标内核头、TLS/线程与 loader 合同，再以独立测试证明行为；不能把 hacker-mode、空目录或通用桩冒充后端。源码签名需通过可信独立来源确认公钥后验证；取得完整宿主工具并记录来源、版本和散列。G1 继续，不将该调查视为 G2 或动态链接完成。

## 继续：NPTL 依赖探针（2026-11-13）

在独立解包副本中进行更深入的**负向诊断**：`--hacker-mode --diagnose-nptl` 创建临时 `sysdeps/xos/Implies` 指向 `nptl`，并添加仅供测试的 ABI tag 255；该数字不是 XOS ABI 分配，不写入候选源码或发行材料。configure 返回 0 仅说明诊断目录组合可生成 Makefile，不能说明 XOS 后端有效。随后 GNU make 退出 2，首先暴露 `bits/semaphore.h` 和 `bits/pthread_stack_min-dynamic.h` 缺失；日志 SHA-256 `2469e67b16fa6c9da9e1e8ce6865dd9189a4062f91966540966aed111c91be43`。诊断入口拒绝无 hacker-mode 的该选项、错误归档与已存在的输出目录；`python3 tests/glibc_g1_probe_test.py` 通过。这些边界测试不是 glibc 功能测试。

| 实际接口 | glibc 2.44 源码依赖 | 当前 XOS 接口 | 尚需证明/实现 |
|---|---|---|---|
| 初始 TLS | x86-64 NPTL `tls.h` 的 `TLS_INIT_TCB_SIZE` 是 `sizeof(struct pthread)`，包含 DTV、自指针及线程描述符 | `src/user/arch/x86_64/tls.cpp` 按 variant II 映射静态模板，在 TP 写自指针并给 TCB 预留 16 字节；`sys_process_tls` 仅允许创建者对 building 子进程设置 | glibc TCB 大小、DTV、对齐、FS 基址变更权和主线程早期初始化必须有独立契约及真实客体证据；不可把现有 16 字节当完整 TCB |
| 创建/退出 | `nptl/pthread_create.c` 使用 `__clone_internal`、退出时的 clear-tid、rseq 与 robust-list 路径 | prepare/start/abort、begin_exit/exit、join/detach，且有每进程四线程、固定 stack/TLS 配额 | 定义成功/失败、发布原子性、线程 TLS、退出通知、清理、join 竞态和限制；不能只映射 syscall 号码，robust/rseq 是否可裁剪须由实际构建配置和语义证明 |
| 等待 | NPTL 的 futex、绝对时限、取消与 robust mutex 语义 | `sys_wait_word` / `sys_wake_word`、绝对单调 deadline，受 XOS 地址与资源约束 | 比较共享/私有等待键、竞态、取消、超时、内存生命周期；共享 futex、requeue、优先级继承和 owner death 不能凭接口同名宣称支持 |
| 启动/动态链接 | glibc startup、辅助向量、解释器与动态 TLS | XOS `_start` 收到 `startup_info`，既有 ELF 解析在用户态；当前 G1 未实现 glibc CRT | 版本化启动与 auxv 约定、真正 XOS 工具链、独立 sysroot、`PT_INTERP` 和隔离资源权限需另行冻结 |
| syscall 与文件 | glibc 内部系统相关头及 errno | x86-64 XOS SDK 使用 `int 0x80` 和 XOS 号；文件经认证文件服务/SDK | 独立 XOS sysdep 调用与错误映射，审查 fd/session/fork/exec/路径；禁止将 Linux syscall 号或 newlib 内部结构当成 XOS ABI |

以上是当前源码比对和诊断，尚无可运行 glibc；已运行探针的 ABI tag 及占位目录不能发布或用于真正目标。下一步应先确定 XOS glibc 线程后端的构造与初始 TLS 所有权，再按真实头、启动和等待语义实现最小静态纵切；签名、工具链、动态装载和授权仍是独立验收。

## 继续：源码签名与密钥有效期（2026-11-13）

从 GNU FTP 取得公开 GNU keyring，SHA-256 `8013de59880f7a59f53b6bd207f4d2a408d67b84a82fa9cba1dbbf443428e2db`。隔离准备 GnuPG gpgv 2.5.24 后，实际验证得到 `VALIDSIG`，签名子钥 `FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A`，主钥 `35B17DF5752577CA0C541CEB94BFDF4484AD142F`；但该公钥环还报告 `EXPKEYSIG`，即使 gpgv 退出 0 也必须拒绝作为有效来源依据。

另外取得更新的 keyserver 公钥（装甲文件 SHA-256 `7305140fd8333ceefcb1a3aa88e78a865672caff82b9f274083b1321f90d178c`，解码后 keyring SHA-256 `4d7c10f67569448dca4901245e896988dadfa1318c208b3f3bbfb92c0fe440cc`）；gpgv 输出 `GOODSIG`、相同 `VALIDSIG` 和主钥指纹，签名密钥未报告 `EXPKEYSIG`。个别无关旧密钥有 `KEYEXPIRED`，不能仅凭这一通用状态判定签名密钥已过期。`scripts/glibc_g1_signature_diagnostic.py` 固定输入哈希和指纹、检查 gpgv 状态并拒绝过期/撤销签名；旧 GNU 公钥环应被拒绝，更新公钥可通过密码学检查。额外对篡改的 RSA 签名进行负向验证，即使相应更新了输入哈希也被拒绝。

**信任仍未完成**：keyserver 公钥的更新、有效期及撤销信息尚未经独立可信渠道确认，gpgv 将指定 keyring 当作信任输入，不能据 `GOODSIG` 推导身份信任。来源锁仍为 `candidate_unverified_signature`，仅供研究。签名核对不改变上述 G1 构建和客体验收状态。
