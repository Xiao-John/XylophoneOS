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

## 继续：XOS 目标对象与隔离头文件探针（2026-11-13）

新增研究用 `src/ports/glibc/sysdeps/xos/`：x86-64 `_exit` 通过 XOS syscall 2 终止进程，意外返回时执行非法指令；`kernel-features.h` 不宣称 Linux 可选内核特性；`bits/stdio_lim.h` 的 `FILENAME_MAX` 为 256 字节（含 NUL），对应现有 XOS 文件路径缓冲界限。该定义是当前能力的候选值，文件描述符及 POSIX 路径语义仍须另行验证。它们不使整个 sysdeps 或运行时成为完成品。

重新从候选归档解包，隔离工具链，指定原本为空的私有 sysroot，以现有 `--hacker-mode --diagnose-nptl` 研究配置运行。构建时 `config-sysdirs` 实际包含 `sysdeps/xos`，编译器实际目标依然是裸 `x86_64-elf`，且配置仍临时使用 NPTL Implies 与合成 ABI tag 255；这些不是正式平台配置。所用编译器 SHA-256 `078530461bdb61bcd19fcb0da101c24d34ab19a924b31c4fc7b54bd5d7607b6f`，候选源码、补丁及 overlay 的散列和完整命令写入私有 report。

- glibc 的 `stdlib/abs.c` 和本端口的 `sysdeps/xos/_exit.c` 经 glibc 对应子目录规则实际编为 ELF64 x86-64 可重定位对象；对象 SHA-256 分别为 `82a2631427ea94843428e95d4029a68ae046780349352293046cbfb1501f3628`、`1a746248f719c2fe779275457d76db78d8bef75e1f46a5711b7c0a656686c4bb`。readelf 检查了符号，反汇编核对 `_exit` 的 syscall 号、`int 0x80`、返回后 `ud2` 与无外部重定位；未运行该对象。
- 尝试在私有 sysroot 安装 glibc 头文件，安装到 116 个文件后退出 2，首个头安装阻塞为 `bits/semaphore.h` 缺失；并行构建退出 2，暴露 `bits/semaphore.h` 和 `bits/pthread_stack_min-dynamic.h` 缺失。已安装文件是**不完整且未经资格认可的诊断产物**，不得作为 SDK。manifest SHA-256 `3d4de5b29b4a89511e25850b2b9b184d63466fdde3d88f147cdd73171af488ee`；抽查 `stdlib.h` 与上游源一致，`bits/stdio_lim.h` 与 XOS overlay 一致。
- `tests/glibc_g1_artifact_test.py` 对实际对象、符号、目标指令、编译依赖路径与散列、头文件清单和抽样来源做检查：依赖只来自解包 glibc、私有构建树或交叉 GCC 自身头目录，未混入 newlib/宿主 libc；该检查通过。`tests/glibc_g1_probe_test.py` 也通过。报告 SHA-256 `3d3a9c6d2474989e54f89d9a57fa2fdbb25731d57cea784f087488e0e12a78ef`；私有路径、日志和对象不作为发行物提交。

G1 仍 **partial**：还没有真实、无合成 ABI tag 的完整 XOS 后端配置，没有完整 glibc 或可用 SDK。下一步须为 NPTL 的线程、等待和信号量定义与实现可维护的 XOS 后端及 ABI，然后从干净输入重跑配置、对象、头文件与来源核验；不能把上述诊断对象当作完整 libc 或客体验收。

## 继续：无合成 ABI 标记的 XOS 配置探针（2026-11-13）

`sysdeps/xos/preconfigure` 使用 glibc 提供的端口预配置入口，仅对 `x86_64/64-xos` 设置 `libc_config_ok=yes` 并明确打印未完成警告。这个变量按上游定义会跳过其不支持平台的检查；它是实验端口的定向登记，**不是上游已支持或 XOS 后端已完成的证明**。`sysdeps/xos/Implies` 明确将 NPTL 选为依赖调查方向，选择源码不代表 XOS 已提供其线程、TLS、futex 或信号量语义。预配置入口对 x32、非 XOS 和其他架构不放行。

`--xos-backend` 从锁定候选归档解出新源码、应用 XOS 三元组补丁并复制仓库中的真实 XOS overlay，不使用 `--enable-hacker-mode`、不修改 `abi-tags`、不生成假的 ABI tag。私有空 sysroot 明确传给交叉编译器，正常 configure 退出 0 且 `config-sysdirs` 选择 XOS 和 NPTL；整体 make 退出 2，最早明确阻塞是上游 `abi-tags` 无 XOS 记录，另有 semaphore、pthread stack minimum 头缺失。`install-headers` 退出 2，在 116 个文件处因 `bits/semaphore.h` 停止。这些失败属于预期记录，不改变后端未完成状态，也不分配未经约定的 GNU OS ABI 标记。

同一干净输入使用 glibc 的实际子目录规则编出 `abs` 与 XOS `_exit` 的 ELF64 对象，SHA-256 为 `7cef76c76fe1cb694a21dbb3b58bf5618961057173d33be5a65f8c8b7beb9644`、`374ceb2cd5e6f647f88482e6ae4cb4ce35ea5758b40aace7cfcecf5b5689c3b3`。对其符号、汇编、依赖边界、头文件内容及散列执行 `tests/glibc_g1_artifact_test.py` 通过；测试还核对归档与锁、上游 `abs.c`、仓库补丁和 overlay、探针与各工具散列、所选 sysdeps、无虚构 ABI tag。目标选择与探针保护测试通过。私有报告 SHA-256 `393d36e4bacba1da1a96ea76905386cc3891a6260abbe40c23c2e098f5756df2`；对象散列绑定当次构建路径，不能当作可重现二进制声明。

```sh
# 在满足工具要求、已设置隔离工具 PATH 的环境中：
python3 scripts/glibc_g1_probe.py --archive "$GLIBC_ARCHIVE" --output "$NEW_SCRATCH" --xos-backend
# 完整构建尚未通过，探针预期非零；继续检查产生的报告和实际对象：
python3 tests/glibc_g1_artifact_test.py "$NEW_SCRATCH" --archive "$GLIBC_ARCHIVE"
python3 tests/glibc_g1_probe_test.py
```

G1 仍未验收：真实 XOS 工具链、正式 ABI note 策略、完整目标头与 libc 尚缺，候选签名的信任状态未变；本次不声称 guest、动态链接或 POSIX 支持。下一步先厘清 XOS 可执行格式与 glibc ABI note 的衔接，再实现有真实语义的目标线程/等待基础，不能为了通过构建复制 Linux 假设。

## 继续：XOS 的 GNU ABI note 构建路径（2026-11-14）

现有 `src/user/loader/elf.cpp` 对 ELF64 ET_EXEC 检查机器、OSABI、边界和 LOAD 等，但对 `PT_NOTE` 跳过内容；不读取 GNU ABI note。glibc 2.44 的通用 `csu/abi-note.c` 需要 `abi-tags` 分配的 GNU OS 编号，而 XOS 目前没有已知分配。研究配置据此选择不发出该 GNU OS ABI note，绝不借用 Linux 编号或保留的虚构数值。此举不提供版本检查或原生/外来二进制区分，也不决定未来 ABI：动态链接的身份、版本与拒绝策略仍须由 D0 冻结并在 D1/D3 验证。

新增候选补丁 `0002-xos-abi-note.patch`（SHA-256 `ad2c03e0613c8765fd4f3033efbf69d6357b39a70547da2fc1186df91aceac52`），仅在 XOS 配置下提供无 GNU OS 标签定义的 `abi-tag.h`，其他配置保留上游路径。实验 XOS 后端提供 `sysdeps/x86_64/xos/abi-note.c`，保留上游 x86 ISA property note 而省去 GNU OS ABI note。实际检测发现放到通用 `sysdeps/xos` 会被更高优先级的上游 x86 文件覆盖，已改为架构与系统组合目录；最终 configure 的 sysdeps 列表与实际编译命令均确认选择后者。

在新的隔离研究输出中，不使用 hacker 模式或合成 ABI tag，正常全构建越过 `abi-tags` 阻塞，仍因 `bits/semaphore.h` 与 `bits/pthread_stack_min-dynamic.h` 缺失退出 2。正常 `csu/abi-note.o` 构建仍被这些前置项阻塞；为了单独验证所选源和 note，额外调用 glibc 子目录 make 并明确清空 `before-compile` 前置项：该**受限单对象诊断**成功，readelf 显示 x86-64 baseline 的 `NT_GNU_PROPERTY_TYPE_0`，没有 `NT_GNU_ABI_TAG`。它不是正常 csu 构建通过，更不是客体测试。其对象 SHA-256 `4289a089ad3e7ace1f795c8ea2e55c1ce9e898b53d13e70eb1a2b4645a35a3f5`；报告 SHA-256 `f18bf43be6bcbd93fb35d6787d158ba2391fbb41829f197c23a71cd5fee1d98f`。

目标对象、编译依赖、sysroot 部分头文件、注册目标限制与报告输入散列的检查均通过，探针与证据路径检查重新执行。G1 仍 partial；下一处实际工作是为 NPTL 与 XOS 线程后端建立真实语义和目标头，而非将跳过前置项的结果当成完整 glibc 构建。

## 继续：线程类型和 x86-64 NPTL TLS 选择（2026-11-14）

根据 glibc 2.44 的 `struct new_sem` 容量/对齐断言，为实验 XOS x86-64 LP64 端口提供 32 字节、8 字节对齐的 `sem_t` 不透明存储；`PTHREAD_STACK_MIN` 取 XOS `thread_abi.hpp` 的 65536 字节原生栈下限，实际 TLS、保护页和运行时所需大小可能更大。线程本地键表在候选 glibc 中暂定 128 个及 4 次析构迭代，均由用户态管理，不改变内核四线程配额。这些是实验 ABI 定义，不证明 sem、线程或 POSIX 运行行为，也未承诺最终发行 ABI。

进一步核查发现，原 `Implies nptl` 没有选中 `sysdeps/x86_64/nptl`，之前生成的配置实际上使用了通用 TLS 头；已有对象和配置报告不能用于证明 glibc TCB 正确。现在架构专属 XOS Implies 显式选中 `x86_64/nptl` 与 `x86/nptl`，并通过 XOS 包装头选择上游 x86-64 NPTL 布局。上游头中的 Linux `ARCH_SET_FS` 与 Linux syscall 不适用于 XOS；候选补丁 `0003-xos-tls-init.patch`（SHA-256 `ca6b676fa71da5dca5ff58ce0da2c10725c0c18fd837c6e99027da3b340646e0`）在 XOS 路径将 `TLS_INIT_TP` 明确设为失败，未实现前不会声称线程指针已安装。当前 `sys_process_tls` 只允许创建者设置 building 子进程，无法充当调用者设置自身 TP 的接口。正式初始化仍须设计/实现并在客体验证。

干净输入采用单线程 make，避免调查时一次并行启动中 `libc-modules.h` 尚未生成的非目标噪声。上游生成的 `sem_t-align.h` 为 8、`tlsdesc.h` 中 `DTV_OFFSET` 为 8，依赖记录同时指向 XOS 包装头和 x86-64 NPTL 头；此前被前置项阻塞的 `abi-note.o` 现可按正常 glibc 规则编译。`abs`、`_exit`、note 对象和头文件来源检查通过；另用 glibc 实际编译参数生成 TLS 初始化探针，目标指令返回失败且没有 `syscall`/`int`。交叉编译静态断言核对 `sem_t` 尺寸/对齐、栈下限与实际 XOS 线程契约、键数。以上是目标构建检查，未运行线程或 glibc 客体。

完整 make 仍退出 2，下一处可见障碍为通用 `bits/errno.h` 明确报移植未完成及 `bits/types/idtype_t.h` 缺失；头文件安装至 184 个后因后者退出 2。私有报告 SHA-256 `361891f1291fafa0deb95221ec8dc469978da5e87eeef06ff7f7a08b6e20af25`，头文件清单 SHA-256 `b25aac0da9cc465c635db18c7392b889aa43858712520fd3ea0d3896a69a1437`。G1 仍 partial，继续处理真实 errno、进程等待类型和后端，禁止复制 Linux syscall 或将上述显式失败当作可运行 TLS。

## 继续：errno、等待类型与真实头文件客户端（2026-11-14）

新增候选 XOS glibc `bits/errno.h`，以数值表独立保存本 libc 的错误码；初始共有 85 个名称（含 `EWOULDBLOCK` 别名），与本机已有 XOS newlib SDK 中同名宏数值对照一致，但不引入其 `errno`、`_reent`、头文件或运行时代码。错误码是用户态 ABI，不能直接把 XOS 各服务/内核的负值取反当作 errno；后续各后端需做实际映射和负向测试。该表目前为候选，非发行 ABI 冻结。增加 `idtype_t` 的 `P_ALL`、`P_PID`、`P_PGID` 类型值，不代表 XOS 已实现 waitid 或进程组。

上游通用 `check_fds.c` 依赖 Linux 风格设备号与 `st_rdev`，不能直接用于现有 XOS。实验端口提供 XOS `__libc_check_standard_fds`：若 glibc 安全启动路径请求检查，而可信标准描述符及 `/dev/null` 契约尚未建立，就以 `_exit(127)` 直接失败，不伪报成功或继续特权启动。交叉编译和反汇编确认选择 XOS 实现，且调用 `_exit`；这不是安全启动或客体验收，D0/D3 仍需完成可信启动、FD 与失败行为验证。

从原始候选归档和隔离工具重跑：glibc `install-headers` 退出 0，安装 335 个文件，清单 SHA-256 `318a2cdd442ca67ce36545a9883bf41b144b068607a84228cec6c8b5ce337840`；然而真实目标客户端包含 errno、stdio、pthread、semaphore 和 wait 头时退出 1，首个错误是缺少只有完整 libc 构建才能生成的 `gnu/stubs.h`。因此命令完成不等于完整、可用的 sysroot；没有人为创建空 stubs 来掩盖缺口。正常完整 make 仍退出 2，进入 NPTL 后缺少 XOS `__syscall_arg_t`、内部系统调用和 futex 后端；必须根据 XOS 实际线程及等待语义实现，不能直接调用 Linux futex。

本次检查覆盖目标 errno/等待类型静态断言、安装文件来源和哈希、实际客户端失败、XOS 安全 FD 函数对象及 `_exit` 重定位，既有 TLS 失败、对象、note 和目标隔离检查也通过。私有 report SHA-256 `66852503a6dd5177aea99972c5fe37099b3d78a2c5cda599bc00ef6de84e922f`。G1 保持 partial，未得到可用 SDK、完整 libc 或客体运行结果。

## 继续：XOS 私有 wait-word 原语（2026-11-14）

新增 glibc 端口私有的 `__xos_wait_word`、`__xos_wake_word`，按 `thread_abi.hpp` 构造版本 1、40 字节请求，使用 XOS syscall 48/49 和 `int 0x80`。等待使用绝对单调时钟纳秒或全 1 的无限期限，按内核原样返回 XOS 结果；唤醒保留内核的唤醒计数或错误。它们只封装同进程地址等待，不设置 errno、不了解 glibc 取消，也不声称 futex、跨进程共享或实时钟语义。XOS sysdeps Makefile 将其登记为 NPTL 私有支持对象；当前 NPTL 尚未调用这个桥，不能据此宣称 pthread 已经可用。

`tests/glibc_g1_wait_test.py` 在宿主以模拟系统调用验证请求布局与内核公开 C++ ABI 的对应、版本、大小、保留字段、期望值、有限/无限截止时间、原始错误及唤醒计数；另以真实 x86-64 交叉编译验证对象中的两条 `int 0x80` 与调用号。测试通过，但模拟不代替客体验证。干净源码构建中 glibc 自身 nptl 子目录规则成功编出 `xos_wait_word.o`，SHA-256 `650f83bc90565866e1edf1189d4d9338c37c2ebaa8d80dc2ed563119ef25254d`；报告 SHA-256 `203275652e2ae6fa3f3eda40f19a292054907df1dbfb0682da38f140c95b6490`，对象/头文件来源与既有探针检查通过。

接入 glibc 的后续工作必须明确处理原始状态到 glibc 可接受错误的转换、因取消/信号引起的中断、无效地址和对象生命周期、资源上限、相对/绝对超时及实时钟、共享等待、robust/PI/requeue 等；不能把不同语义直接包装成 Linux futex 成功。完整构建当前仍在 NPTL 的内部 syscall/futex 接口处失败，安装的头缺少生成的 `gnu/stubs.h`，故 G1 和客体资格仍未完成。

## 继续：NPTL 私有无时限低级等待接入（2026-11-14）

为 glibc `lowlevellock-futex.h` 增加 XOS 覆盖，使 `lll_futex_wait` / `lll_futex_wake` 的**进程私有、无超时**路径调用上一步的 XOS wait-word 桥。候选适配器把 XOS value-changed 映射为 `-EAGAIN`，地址、超时、无效参数与资源错误分别映射到 libc errno；成功唤醒返回 glibc 低级接口要求的 0，而不是误把唤醒个数视为错误。errno 是 libc 值，不把任意 XOS 内核返回值取反。未知结果返回 `-EIO`，不会被当成成功。

XOS 目前没有相同语义的跨进程共享 futex、低级定时等待、取消入口、requeue、wake-op 或 PI；这些路径明确 trap，时钟支持查询返回不支持，避免静默丢失唤醒或调用 Linux syscall。这是保守的实验失败策略，尚非 POSIX 线程实现；以后需要由 API 层及语义完整的后端给出适当错误与行为，不能把 trap 当作最终用户接口。

模拟测试验证 XOS 请求和 glibc 低级结果转换，包括值变化、无效地址、超时、资源和未知错误、唤醒计数及无效计数；目标交叉编译核对真实 syscall 指令。另用真实 glibc 编译配置编译低级宏探针，检查私有等待/唤醒分别引用 XOS 适配器、共享路径包含 trap；构建中的依赖文件确认优先选择 XOS 覆盖头。两份 XOS 原语和适配器由 glibc 的 nptl 子目录规则编成目标对象，适配器 SHA-256 `d6b4b65fa7050867642168b4788b441211af8b752d9b6818f25884ed0bdcc899`，完整研究报告 SHA-256 `1b0ea29faa064b96b8587afe7549b4c47e6bd0dc700a657eb2c50368f1687d14`。探针、对象/头文件来源检查通过，尚无客体证据。

完整 make 仍退出 2，首批剩余错误包括缺少 XOS 的 `__syscall_arg_t` 和 `INTERNAL_SYSCALL_CALL`；目标客户端仍因 `gnu/stubs.h` 缺失不能使用 sysroot。G1 保持 partial，下一步处理 XOS 实际系统调用约定及 glibc 启动/取消依赖，持续保留不支持项的真实失败。

## 继续：系统调用入口与非末线程退出（2026-11-14）

新增 XOS x86-64 `sysdep.h`，沿用 glibc 通用参数类型但只把明确实现的名称派发给 XOS 入口；未知名称在当前构建中报错，不翻译成同号 Linux syscall。新增 `__xos_internal_exit`：先调用 XOS `sys_thread_begin_exit`，确认不是最后线程后才调用 `sys_thread_exit`；如结果为最后线程、握手失败或线程退出意外返回，则以进程退出码 127 失败收束，避免跳过 glibc 最后线程收尾。宿主模拟验证 syscall 顺序、非末线程参数及末线程/错误回退；交叉对象检查了 42、43、2 号 XOS 中断及返回后的 trap。实际 NPTL 主线程退出还涉及取消、join 及共享等待；当前相关路径仍不完整，不据此宣称 pthread 或客体通过。

实验构建添加 XOS 私有 `shlib-versions`，暂用 `libc.so.0.1`、`libm.so.0.1` 和 `GLIBC_2.44` 起始版本，使生成器能够给 libc/libm 分配模块号。它们仅是当前隔离构建候选，不是冻结发行 ABI、解释器路径或 Linux 二进制兼容承诺；动态链接身份和兼容规则仍受 D0–D4 门约束。目录流只以前置声明暴露不透明类型；需要目录流布局或功能的代码仍须等真实文件服务后端，不伪造实现。

GNU glibc 2.44 的通用 `sigset` 失败桩在目标 GCC 16 下因返回整数 -1 而无法编译；候选补丁 `0004-sigset-error-pointer.patch` 将其改为标准 `SIG_ERR` 指针，仍设置 `ENOSYS` 且保留 stub 标记，不宣称信号可用。交叉对象反汇编确认该失败值与错误码。干净构建继续到上游通用 `raise` 的 `gsignal` 别名/隐藏符号冲突，完整 make 退出 2；头文件安装仍完成 335 项，但目标客户端缺少 `gnu/stubs.h` 而失败，sysroot 未获 SDK 资格。

生成的 XOS 线程退出和 `sigset` 对象 SHA-256 分别为 `d18ca95e3c6d075c1ac8c9901e5b276ac9e4591f9019b837e6b4845e83a7139d`、`cbcffdbc4eccc397645cbac31d71800b7d21da0d258ebbb26b1c7d13d1b0db5e`；报告 SHA-256 `339e7b9be40e945543ea8658912e9e235fab16e0dfc72263be15c3e3dbfe879b`。目标来源、对象、模块版本、未知系统调用拒绝、等待桥、线程退出和 ABI 选择检查均通过；未运行客体。G1 仍 partial。

## 继续：信号失败桩、线程锁与 libc 交叉构建（2026-11-14）

修复 glibc 2.44 通用失败桩在共享构建中遗漏隐藏符号定义的问题：`raise` / `gsignal` 继续设置 `ENOSYS` 并失败，`sigwait` 直接返回错误号 `ENOSYS`，符合该接口的返回约定，不宣称 XOS 已实现信号。目标共享对象实际导出 `raise`、弱别名 `gsignal` 和隐藏入口；`sigwait` 对象导出对应入口，反汇编确认直接返回错误号且不修改 errno。候选补丁的输入和哈希记录于 report。

`arc4random.c` 显式包含其使用的原子操作头，XOS 线程配置使用 glibc 的保守 `SINGLE_THREAD_P == 0`，始终走锁路径，不能假设运行时始终单线程；XOS stdio 锁包装头显式引入 `EBUSY` 定义。错误文本复用 glibc GNU 通用的符号描述，但使用 XOS 候选 errno 数值；XOS 候选 profile 从 `GLIBC_2.44` 起，没有历史信号列表版本可导出。这些修改均不保证随机数、线程或信号功能可在客体运行。

干净归档、私有 sysroot 和已记录工具链构建已越过前述失败，`signal/raise.os`、`signal/sigwait.os` 和 `stdlib/arc4random.o` 均实际产生并记录散列。完整 make 下一处失败是 `libio/freopen.c` 所需 `arch-fd_to_filename.h` 尚无 XOS 实现；XOS 当前不能假定 Linux `/proc/self/fd` 语义。头文件安装退出 0，但目标客户端仍缺少由完整 libc 生成的 `gnu/stubs.h`，不是合格 SDK。报告 SHA-256 `224b1d83e87b7762641d2e18011a3f14ab37184e5cacf16413842bbbb6ee0511`。

目标对象符号、失败语义、补丁与工具散列、保守锁路径、wait 和线程退出模拟、探针保护及依赖来源检查通过；未运行完整 libc 或客体。G1 继续为 partial。

## 继续：无描述符路径时的 freopen 失败路径（2026-11-14）

XOS 当前没有可用来重开任意已打开文件描述符、且与 Linux `/proc/self/fd` 等价的文件服务契约。新增 XOS 私有 `__fd_to_filename`，明确返回空指针和 `ENOTSUP`；候选补丁使 `freopen` 与 `freopen64` 检查该失败，关闭原文件流、保留错误并返回失败，而不是将空路径传给打开函数或构造未经授权的伪路径。有文件名的原有路径保留；`freopen(NULL, ...)` 在此实验后端尚不支持。该失败分支尚未在客体运行，不能视为完整 stdio 资格。

独立宿主测试核对路径转换对有效及负描述符均返回空指针并设置 `ENOTSUP`；干净 XOS 目标构建实际生成 `fd_to_filename.o`、`freopen.o`、`freopen64.o`，对象来源及调用引用检查通过。`dlerror.c` 对 `__set_errno` 增加显式 `<errno.h>` 包含，避免依赖 Linux 头的间接包含；这只是编译修正，不意味着动态加载已实现。

完整 make 已继续到 `nptl/cancellation.c`，在取消系统调用参数宏缺失处退出 2；不可借用 Linux 可取消 syscall 汇编来宣称支持。头文件安装仍完成 335 项，独立客户端因未生成 `gnu/stubs.h` 失败，sysroot 尚不可用。报告 SHA-256 `4d7627f3999bef3d917a40e01ac30d6b6c236f39ecc5a3bd68f57561f43eddcf`；描述符转换、等待桥、线程退出、目标符号与探针保护检查通过，尚无 glibc 客体运行。G1 继续为 partial。

## 继续：取消系统调用的明确失败边界（2026-11-14）

现有 XOS 线程契约不支持异步取消，不能借用 glibc 的 Linux `SIGCANCEL`、可取消 syscall 汇编与无副作用的 `EINTR` 假设。实验 XOS 后端补齐 glibc 所需的非七参数声明，提供受限的取消 syscall 入口：内部约定返回 `-ENOSYS` 且不改 errno；公开约定返回 -1 并设置 `ENOSYS`；意外进入取消展开入口时 trap。这些入口不执行传入的系统调用、不假装关闭取消后操作成功，也不提供 pthread 取消功能；实现真正取消及正确的非取消运行路径仍是后续工作。目标对象中这三个内部符号均隐藏，避免成为新公共 ABI。

宿主负向测试验证两种返回约定和 errno，目标对象反汇编确认返回值、失败 trap 且无 syscall 指令；目标对象 SHA-256 `d8879cfd3a207249c87879cf4f28b39e2197f2dfee5a475e07c1a733cfa6aff2`。干净构建越过原 `cancellation.c` 参数错误，下一阻塞在上游 `futex-internal.c` 对原子头及 Linux futex/可取消 syscall 的依赖。已有私有无超时 wait 桥不能自动等同于其定时、实时钟、取消、共享和 PI 语义。头文件安装仍为 335 项且目标客户端缺失 `gnu/stubs.h`；完整 libc、SDK 与客体运行均未通过。

取消负向测试、wait 桥、线程退出、描述符失败、探针防护与对象/符号/来源检查均通过；报告 SHA-256 `9e212c0d9e2b45ed63a4c821c4c4e3667e7d9e9400c6a43601b29e11d719f45a`。G1 保持 partial。

## 继续：单调绝对时间等待（2026-11-14）

新增 XOS 私有单调时钟等待转换及 glibc `__futex_abstimed_wait64` 的实验后端：绝对秒/纳秒转换为 XOS 纳秒期限，保留空超时的无限等待；负秒返回 `ETIMEDOUT`、非规范纳秒返回 `EINVAL`，无法表示的有限期限及与 `UINT64_MAX` 无限哨兵冲突返回 `EOVERFLOW`。XOS 原始值变化与超时映射到 glibc 错误，glibc 调用方不会处理的其他内核/资源错误调用 fatal，避免被忽略后无限重试。该接口只处理私有单调等待，不处理 realtime 或跨进程共享。

可取消等待和进程共享路径明确 trap；PI 路径也 trap：审查发现部分 NPTL PI 锁调用方不会检查 `ENOTSUP`，若简单返回该值可能错误地继续执行并当作已获得锁。当前 `futex_abstimed_supported_clockid` 仍不对外宣称时钟支持，相关 API 尚未验收，不能以这个内部片段声称条件变量、取消或 POSIX 线程可用。

宿主模拟测试覆盖有限和无限期限、边界及溢出、无效纳秒、原始错误转换，以及共享/取消/PI/意外错误的终止分支；目标编译实际选中 XOS `futex-internal.c`，生成的两个目标对象分别为 `a198e2cd8f7f93d47c0e18f375bc854a5a7cdf970363a38dcb0dc1a1b1be94a0`、`95ce27777718c6cdf10991be031e00c8868cd5205b16cc24ef77ed56ad95f77c`。现有取消、线程退出、路径、wait 桥、符号、来源与探针检查通过，未运行客体。

完整 make 已越过原 Linux futex 接口错误，下一阻塞为上游 `nptl_setxid.c` 依赖 Linux `SIGSETXID`、`SI_TKILL` 和系统调用约定；它须与 XOS 权限/身份模型对齐，不能伪造 Linux 凭据语义。独立头文件客户端仍缺少 `gnu/stubs.h`。报告 SHA-256 `3337b801a6fd06c24ae34b1d30ba618c055186a7ae5c5782255862d56fad4dac`；G1 仍 partial。
