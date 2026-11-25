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

## 继续：凭据切换与 pthread 取消的真实失败（2026-11-14）

依据 [XOS 权限设计](../plans/permission_model_glibc.md)，`set*id` 身份切换尚未实现，uid/gid 也不能自行扩大 authority。XOS 后端的 `__nptl_setxid` 不调用 Linux syscall、不发送 `SIGSETXID`，保留请求内容并返回 -1、设置 `ENOSYS`；误入 Linux 式凭据同步信号处理入口时 trap。这个实验入口不提供身份切换，不决定后续身份/委派契约，也不以 uid 值授权。

当前 XOS 线程契约不支持取消，目标 `pthread_cancel` 因此按 pthread 约定直接返回 `ENOTSUP`，不修改 errno；不采用 Linux 的 `SIGCANCEL` 与 `SI_TKILL`。宿主负向测试验证凭据请求不变、失败返回及处理器 trap，另验证取消错误和 errno 不变；目标对象符号、错误值、隐藏可见性及无 Linux syscall 的检查通过。真实 XOS 客体、信号及 pthread 取消行为尚未验收。

从锁定归档干净重建时，完整 make 越过凭据同步及取消源文件，继续至 `pthread_create.c` 缺少 `rseq-internal.h` 退出 2；rseq、线程创建和 TLS 仍须依赖实际 XOS 后端，不能只复制 Linux 定义。`install-headers` 完成 335 项，独立目标客户端仍因缺少 `gnu/stubs.h` 失败。`nptl_setxid.o`、`pthread_cancel.o` 的 SHA-256 为 `ff29ed23de54dfbd11bd6aed892e19362a516348fa18ff007da4e75d4a33468d`、`5187234f829b607bb2cc23eaedf1dbc34502f99248d9b34de8831b2b4889e122`；报告 SHA-256 `54f86b1116d22fa2339ee448a952547dcd290b60b892d3d3b4ad4010cfd1275e`。全部现有 G1 宿主/目标对象探针通过；完整 libc、SDK 和客体运行未通过，G1 保持 partial。

## 继续：明确禁用未实现的 rseq（2026-11-14）

XOS 当前无 restartable-sequences 内核协议。实验 NPTL 的 XOS `rseq-internal.h` 对唯一已调查的 `cpu_id` 查询返回负的未注册状态，注册请求无论是否要求都返回 false；若上游线程创建把它标为必需，其现有检查将失败而不声称注册成功。未知字段没有定义，避免凭空提供其语义。这个内部回退不实现或认可公开 rseq ABI、rseq TLS 布局，也不使线程创建可运行。

宿主测试覆盖未注册状态、请求与不请求均不返回成功，以及未知字段编译失败。干净构建越过 `rseq-internal.h` 缺失，下一处 `pthread_create.c` 失败为缺少 Linux `clone3.h`；真正的 glibc 线程创建必须接入 XOS prepare/start、TLS 和退出契约，不能将 clone3 号码或结构当作 XOS ABI。其他既有目标对象、wait、取消、身份及来源探针通过；头文件安装 335 项但目标客户端仍缺少 `gnu/stubs.h`。私有报告 SHA-256 `6f219c929c91f427e02bc142b9de82bbe0781375f28778241e01a47ac3c89800`。未运行客体，G1 仍 partial。

## 继续：XOS 线程预留与启动的底层桥（2026-11-14）

新增私有线程桥，按现有内核契约构造版本化 prepare/start 请求并调用 XOS 38、39、40 号接口，返回未经转换的内核结果。成功预留后由调用方负责 TLS 初始化、启动及失败时撤销；撤销失败仍须保留资源所有权。桥本身不实现 pthread 创建、线程 ID 发布、TLS 布局或资源回收策略，不能作为可用线程的证明。

宿主测试对照内核共享 ABI 的结构大小和字段位置，检查请求内容、原始成功与失败返回；目标反汇编检查三个 XOS 陷入和调用号。既有 G1 模拟与目标对象测试通过。干净归档构建生成目标桥对象，SHA-256 `c60ce75d007a6e9a5fea3240a5a8e303315254ff5f965f3a5cb4d34572ded070`；来源、符号及探针检查通过，报告 SHA-256 `e7054bdfccac3fe18459de5364aa0c798439be5ca3a4187083e4d30b079d12e2`。

完整构建仍在上游 `pthread_create.c` 的 Linux `clone3.h` 依赖处失败；独立 sysroot 缺少 `gnu/stubs.h`，未进行客体验收。G1 仍为 partial，下一步需要把真实 glibc 线程创建、描述符和 TLS 生命周期接入 XOS 契约，而不是把该桥当成完成的实现。

## 继续：线程启动事务和回收错误（2026-11-14）

在线程原始桥之上增加内部启动事务：先预留、在调用方初始化栈和 TLS 前发布暂定 ID，再启动；初始化或启动失败时撤销预留，保留原错误并单独返回撤销错误。撤销成功清除暂定 ID；撤销失败保留该 ID，交给调用方查明状态或处理，而不假设撤销失败后资源一定仍存在。此 API 不持有外部回调数据，也不实现 glibc 的 `pthread_create`、TLS 或 join。调用者必须在成功启动前完成所有线程可见数据的初始化，并自行保证参数生命周期。

重新对照 glibc 2.44 与 XOS 内核：glibc 的 `allocate_stack` 将描述符和静态 TLS 安排在其分配的栈区域，`pthread_create` 使用 Linux clone，并依赖退出时内核清除 join 状态；XOS 则分别预留固定范围的栈和 TLS，使用 prepare/start，退出走独立协议。现有桥不能消除这些差异，后续必须同时解决布局、入口和退出/join 生命周期，不可仅补 `clone3.h`。

宿主模拟覆盖预留失败、初始化失败、启动失败、撤销成功/失败、先发布 ID 和正常启动；现有 G1 测试通过。干净构建的线程桥目标对象 SHA-256 `e7aab3265fd7b6187738d1f6edd72a747a895d5a15d9c39206e48a12f0086116`，来源和符号检查通过；报告 SHA-256 `cd43e9b22708c4e766c74d68b10069c8c0bbb79d94b4e73984efa0bd695197ed`。完整构建仍在 `clone3.h` 处失败，目标客户端仍缺 `gnu/stubs.h`，未做客体验收，G1 仍为 partial。

## 继续：所有诊断对象的依赖来源（2026-11-14）

此前仅对 `abs` 和 `_exit` 检查完整编译依赖路径，其余对象只核对实现路径，不能证明头文件未混入宿主或旧 SDK。探针现在对每个成功生成的诊断对象解析实际依赖，检查依赖文件与对象的对应关系，将每个输入的 SHA-256 纳入报告绑定的清单，并仅允许候选源码树、私有构建树和交叉编译器内置头目录；路径解析后仍检查边界，以拒绝逃逸符号链接。

验证器从锁定归档独立恢复补丁涉及的原始文件并重放仓库补丁，再将全部源码依赖与归档、重放结果或 XOS overlay 比较；生成文件和编译器头也与清单绑定。模拟测试覆盖外部头、未知变量、错误对象、越界符号链接及生成头内容变化。此检查验证被记录的诊断对象的编译输入，不证明完整构建、运行行为或候选源码签名的信任状态。

最终干净运行覆盖 15 个对象、247 个不同依赖（源码 240、构建生成文件 3、编译器头 4）；来源及既有 G1 测试通过。依赖清单 SHA-256 `fe3af1f3c007b8f043f8391135ddbeb3dfdc04388ffdf196ad0911240002b952`，报告 SHA-256 `32815f583d54f2b6e71d786470007bf5617a653aef2d85b967e35cadd12f2240`。完整构建仍因 `clone3.h` 阻塞，头文件客户端仍缺 `gnu/stubs.h`，未进行客体验收；G1 仍为 partial。

## 继续：独立 TLS 预留区中的 glibc 布局（2026-11-14）

XOS 为新线程分别预留栈和 TLS；glibc x86-64 使用 `TLS_TCB_AT_TP`，静态 TLS 在 TP 之前，`struct pthread` 从 TP 开始，loader 的静态大小包含描述符。新增私有布局计算：使用调用方提供的实际静态大小、对齐和描述符大小，在内核给出的 TLS 范围内计算静态区域、TP 和描述符末端；检查尺寸、对齐、越界和整数溢出，失败不修改输出。此计算不分配或初始化 TLS、DTV 与线程描述符，也尚未接入 `pthread_create`。原始线程桥注释同时修正为：撤销失败时由调用方查明状态，不能断言预留必然仍存在。

宿主测试覆盖多组对齐与地址、空间不足、非法参数、溢出及失败输出；目标编译以实际 glibc `TLS_TCB_SIZE` 和所选 x86-64 TLS 定义编译调用，并核对桥目标符号、全部诊断对象来源和既有回归。完整 make 仍在 `clone3.h` 处失败，客体、TLS 初始化和 join 均未验收，G1 继续为 partial。桥对象 SHA-256 `bce57c7178d77f8f2244e670b2d3166964f07f7c689d121c1ee326fbc8caea54`，报告 SHA-256 `776d7d5c5cb77e0d242638c658566b0e9c017a2226adab8242f2d8926ed98e45`。

## 继续：线程 TLS 初始化及启动前回滚（2026-11-14）

在已验证的 XOS 预留区布局上，新增 glibc 私有 TLS 初始化：使用实际 loader 静态大小和对齐计算位置，初始化线程描述符中必要的自指针、首个 TSD 块和 setxid 状态，并调用 glibc `_dl_allocate_tls` 分配 DTV、初始化静态 TLS。布局失败和 DTV 分配失败分别返回，失败不发布描述符。新增只用于启动前回滚的清理入口，调用 `_dl_deallocate_tls(..., false)`，不释放内核拥有的 TLS 区域。线程启动事务增加回滚回调，在 setup 或 start 失败时先执行调用方清理，再尝试 abort；保留原失败与独立的 abort 错误。

模拟覆盖 DTV 分配失败、预留区不足、启动失败时先释放 DTV 再撤销预留，以及 setup 失败时无误释放；既有测试通过。干净目标构建实际使用 glibc 内部定义编译 TLS 初始化对象，并检查符号与完整依赖来源；对象 SHA-256 `4a4317005b6f22e3ea85f13a78485b22fd9843c512191648765fbff2e0785f02`，报告 SHA-256 `be2596ca2771c41da503c34578b32e18e7932e8867d4103e40dd39ef83b3a656`。

这仍不是可运行的 `pthread_create`：上游栈分配、入口、描述符注册和 join 尚未接入。尤其 XOS 内核回收死线程时先释放栈/TLS 页面，再唤醒 joiner；因此不能假定 join 后还能访问描述符并执行 glibc 常规清理。正常线程退出的 DTV、描述符与结果生命周期需要另行实现和客体验证，不能把启动前回滚接口用于该路径。完整 make 仍阻塞于 `clone3.h`，独立头文件客户端缺少 `gnu/stubs.h`，G1 仍为 partial。

## 继续：原生线程桥的真实客体子集（2026-11-14）

新增不链接任何 libc 的独立 XOS 客体探针：从实际线程桥源码编译 ELF，在内核中验证先预留后启动、故意传入无效入口后的回滚和撤销、再次创建后子线程读取其 FS 指向的 TLS、线程退出值及 join，并对每次进程退出检查系统资源恢复。脚本核对构建清单所列源码、系统镜像、编译器、探针输入和产物散列；它仅验证原生桥，不是 glibc 或 pthread 客体验收。

一次四轮客体运行通过，资源均恢复至 `[129725, 3, 1]`；该次系统 build ID `87a0758ede3091cc`，镜像 SHA-256 `8c734faed0925f64bb0415e9c52d0d33a357510f6c9a4bff244fb0562ad85538`，探针 SHA-256 `68043603113eb843cbd97301dd9b1ab76cdbb672d2fb228f2c78d4d4ddf6beba`；完整本地报告记录实际镜像、清单、源码及编译器。最终提交后的系统和探针仍需重建、重新运行以获得最终组合证据。完整 glibc 构建、真实 glibc TLS、线程描述符和 join 的生命周期尚未完成，G1 仍为 partial。

## 继续：按上游实际规则核对 TLS 地址（2026-11-14）

glibc 2.44 的 `_dl_determine_tlsoffset` 将 TCB 前的静态 TLS 区域向 loader 所需对齐取整；其 `_dl_tls_block_align` 从对齐后的静态区域首地址推导 TP。此前 XOS 布局函数接受前缀不满足该对齐的参数，可能让 TLS 数据不满足实际对齐；同时零地址会使 `_dl_allocate_tls(NULL)` 走自行分配路径。现已拒绝这两种输入，失败保持输出不变。

新增测试从散列锁定的候选源码归档提取原始 `elf/dl-tls_block_align.h`，直接编译其函数，并与 XOS 布局结果比较，覆盖多个对齐、起始偏移和静态 TLS 大小；宿主边界与既有回归通过。此比较仅验证地址计算，不意味着实际 glibc TLS 初始化、pthread 生命周期或完整 SDK 已验收。最终组合需重新构建目标对象并运行客体桥；G1 保持 partial。

## 继续：进程间信号量初始化的真实失败（2026-11-14）

为避免用临时替身掩盖首个阻塞，针对上一轮独立候选构建执行 `make -k` 收集后续独立错误，日志 SHA-256 `08dca447adf69093bfd8d5edc84b8ecf7474357af68695cfb45294add4ac4f5c`。除 `clone3.h` 外，还暴露调度亲和性、线程 CPU 时钟、信号和其他目标头/接口缺口；这些错误可能互相连锁，不能把错误条数当成独立实现工作量或构建成功。

其中确认上游 `sem_init` 对 `pshared != 0` 原本会返回成功，而 XOS 当前 wait/wake 只支持进程内键。候选 XOS 补丁保留 glibc 进程内初始化和超限 `EINVAL`，对非零 `pshared` 在修改对象前返回 `ENOTSUP`；补充候选 NPTL `SEM_VALUE_MAX`。这不实现或认可进程间信号量，也不证明进程内信号量等待、取消或整体 pthread 可用。

基于散列锁定归档提取并应用补丁的宿主测试覆盖共享参数、边界、对象不变及私有初始化；干净目标构建生成补丁后的 `sem_init.o`，SHA-256 `c38c5e102f4f04d0fac6891575e42494ab230789ae838b9bb1b05d2cb4c976eb`，对象、符号和所有依赖来源检查通过，报告 SHA-256 `ea4072392dc97ccd2a986ff24e34b1392d4e6bd74be4416cdecfca6809313010`。既有宿主测试通过；完整构建仍在 `clone3.h` 停止，缺少完整目标头和客体验收，G1 仍为 partial。

## 继续：NPTL 类型来源与信号量发布目标对象（2026-11-14）

`make -k` 揭示 glibc NPTL 的 `internaltypes.h` 使用 `struct sched_param`、`cpu_set_t` 却依赖间接包含；`sem_post.c` 使用 `SEM_VALUE_MAX` 也未显式包含 `<limits.h>`。候选补丁分别补充 `<sched.h>` 与 `<limits.h>`；类型来自 glibc 通用头，不代表 XOS 已实现 CPU 亲和性或调度策略。

从散列锁定归档提取并补丁的 `sem_post.c` 在宿主模拟中检查递增、上限 `EOVERFLOW`、不必要时不唤醒及存在等待者时唤醒一个；这不证明并发、等待或客体语义。干净 XOS 目标构建实际生成 `sem_post.o`，并确认其引用 XOS 私有唤醒桥和意外错误终止入口；对象 SHA-256 `6e1406e340f7559f7ef2f59b6154270b65b6c16ef6476cfcaf03bcd121d2bd48`，报告 SHA-256 `91a67e238fa40779b10f127d01a011461c191659d04eb8f9a431cf5ab801f861`，补丁、对象和所有依赖来源检查通过。完整构建仍在 `clone3.h` 失败，未做 glibc 客体验收，G1 仍为 partial。

## 继续：使用原生调度让出的 glibc 目标对象（2026-11-14）

glibc 通用 `sched_yield` 返回 `ENOSYS`，但 XOS 已有 syscall 3：直接交还调度器，恢复后不承诺 RAX 为返回值。新增 XOS 目标实现发出该调用并返回 0，不把恢复后的寄存器误作 Linux 错误码，保持 errno；不声称实时调度、亲和性或其他调度接口可用。

宿主模拟验证调用及 errno，干净候选构建生成 XOS 目标对象，指令、符号及依赖来源检查通过；对象 SHA-256 `523e7a2ece82c6b037ce6bee0915d804da6c2ac6e56b9346b3e0a4d11b9a5b70`，报告 SHA-256 `42915e64802f09e252198968ad4c990939fa956fef2cb9998a2b67a5587ae5f7`。客体桥探针增加可选模式，将这份真实目标对象与无 libc 的测试程序链接，在两个 XOS 线程间检查让出与资源恢复；提交后的系统须重建并运行该模式，结果记在本地客体报告。此子集不证明 glibc SDK、pthread 或完整构建通过；G1 继续为 partial。

## 继续：进程标识查询与位宽边界（2026-11-14）

XOS 原生 `sys_getpid` 返回所属进程的正 64 位标识；当前 glibc 通用候选 `pid_t` 是有符号 32 位。新增实验 XOS `getpid`：能表示时原样返回，不可表示时返回 -1 并设 `EOVERFLOW`，异常非正值返回 `EIO`；禁止截断成另一个合法身份。这个溢出失败不是对 POSIX `getpid` 总是成功的完整实现：最终原生 `pid_t` 位宽与相关结构和接口仍需整体裁决，不据此冻结 ABI 或声称无限生命周期合规。

宿主模拟检查最小值、最大可表示值、溢出、异常返回及成功时 errno 不变；真实目标对象使用 XOS syscall 6，符号和全部来源检查通过。对象 SHA-256 `39d2482a67ecac045312714dbaa695bd5447563ea35960f9e6b034bcf533f045`，报告 SHA-256 `f2c614fc848cb06b0d20569526219059b1c0a72301d80573985532fadccad4b0`。客体探针可选择链接实际目标对象，并比较主线程和子线程的进程 ID；最终提交后须重新构建系统运行该子集。完整 glibc、pthread 和目标 SDK 未完成，G1 仍为 partial。

## 继续：原生时钟查询与 PID 位宽调查（2026-11-14）

XOS 提供单调纳秒 syscall 46 和 UTC 实时纳秒 syscall 64。新增实验 `clock_gettime`：对单调和实时时钟转换秒/纳秒；未知或尚未接入的时钟返回 `EINVAL`，无效 RTC 返回 `EIO`，单调值超出带符号返回范围时返回 `EOVERFLOW`。这不是完整 POSIX 时钟：CPU 时钟尚未接入，用户指针故障语义和 RTC 异常的客体验证均未完成。

宿主模拟覆盖时钟选择、纳秒转换、错误与失败时输出不变；干净构建生成目标对象并检查符号、陷入与来源。对象 SHA-256 `e0dd272bb7c3ce3758ea5ffb139a261e8aad1c78493c2a91802dea698e776765`，报告 SHA-256 `2df77ebd0a8b4318884d1ca76da6136b742a5a2ce90263e858143fbccc127bd4`。客体桥探针可链接该对象并与内核原始单调计时对照，未知时钟检查真实 errno；最终提交后需重建系统运行该模式。

另核对 64 位 `pid_t` 可行性：上游通用 `setpgid` 参数及 `getppid`、`setsid` 返回值直接使用 `int`，而声明使用 `pid_t`；`siginfo_t` 及 NPTL 描述符也包含该类型。因此不能只改 `__PID_T_TYPE` 就冻结 64 位 ABI，仍须逐项处理类型、结构、接口和旧 SDK 兼容。当前 `getpid` 超范围失败仍是明确的未完成限制。完整 libc、SDK 和线程纵切片均未验收，G1 保持 partial。

## 继续：当前进程与线程 CPU 时钟（2026-11-14）

`clock_gettime` 接入已有的 XOS `sys_process_cpu_time` v1，分别返回当前进程和当前线程的 user+system 纳秒总量；请求使用私有 C 布局，宿主编译逐字段对照共享 ABI。计数器不可用、资源不足、其他内核失败及累加溢出分别映射为 `ENOTSUP`、`ENOMEM`、`EIO` 和 `EOVERFLOW`，失败不写输出。其他进程/线程的 CPU 时钟、用户指针故障及完整 POSIX 时钟语义仍未实现或验收。

宿主模拟覆盖两个时钟的字段选择、转换、溢出和错误；目标对象及全部依赖来源检查通过。目标对象 SHA-256 `6309c5883c74e1cf893ec4ff2bbaa8e53f512e1763c12cf378c7f5afbf714e4f`，报告 SHA-256 `57751a7b9a8b7a1c938152eadde9afc95f85bd86d0640c0c5cdfddbf3c409775`。客体探针对照同一进程的内核原始计数，若计数器不可用则检查明确失败；最终提交后重新构建并记录实际可用状态。完整 libc、SDK 和 pthread 仍未完成，G1 保持 partial。

## 继续：时钟精度查询（2026-11-14）

XOS 单调时钟和实时钟按现有契约使用 syscall 46 的分辨率；当前进程与线程 CPU 时钟使用版本化 CPU 计数响应中的分辨率。新增候选 glibc `clock_getres`，支持标准允许的空结果指针；对未知时钟、计数不可用和异常分辨率明确失败，不虚报精度。`clock_gettime` 与 `clock_getres` 共用私有原生陷入封装，不使用 Linux 系统调用号。

宿主测试覆盖四类时钟、空指针、换算、零值和内核错误；干净目标构建与全部对象来源检查通过。`clock_getres.o` SHA-256 `13cd309eeab6f6265aca6902dc66ee10036d5296a3412bba2dca0bcf22b24c09`，报告 SHA-256 `4cfb86c176cb90d3dfc88b048e43ad5b29898d19ee79d5ad9ac70df25f207fe3`。扩展的客体探针将目标对象与内核原始精度对照，并区分 CPU 计数可用与不可用；提交后须重新运行。其他进程/线程的 CPU 时钟、用户指针故障和完整 libc 尚未验收，G1 仍为 partial。

## 继续：独立 sysroot 的头文件安装检查（2026-11-15）

修复 XOS 栈下限头未被安装的问题，两个 `bits/pthread_stack_min` 头现由 NPTL 安装。独立 sysroot 安装 337 个文件；普通目标客户端仍因缺少最终 `gnu/stubs.h` 失败。为检查后续头文件，在 sysroot 之外使用锁定 glibc 源码自带的构建期占位头进行单独诊断：errno、stdio、pthread、semaphore、wait 和 limits 头及关键布局/常量可编译为目标对象，依赖来源检查通过。占位头没有安装进 sysroot，该结果不构成完整 SDK 或运行资格。

探针报告 SHA-256 `4c49131359e309993d0fad0e647ed82ecd119791dd24eaf92751c696fd34fba2`。完整 libc 构建仍未通过，G1 保持 partial。

## 继续：公共 C 头的独立包含检查（2026-11-15）

扩大安装头文件的诊断范围，发现 `sys/socket.h` 使用 `ssize_t` 时未包含其类型声明；候选补丁显式包含 `<sys/types.h>`，不代表 socket 运行功能已实现。使用锁定 glibc 自带的构建期占位 `gnu/stubs.h`、独立 sysroot 和交叉编译器，逐个检查 150 个公共 C 头，全部通过；Fortran 专用头、内部头及上游故意拒绝的 `regexp.h` 不在此检查范围。目标对象、补丁及依赖来源检查通过。

报告 SHA-256 `9603cdc12e02cb60b5a135b5a708c5bcf60fcd88e3c7ae5098bab776165c277d`，扫描 SHA-256 `bafcd65ced17e1405bea1fc9bcd76e18744715ae35735c5ec290a0bd8ddcd494`。占位头未安装入 sysroot；普通客户端仍缺少最终生成的 `gnu/stubs.h`，完整 libc 构建仍失败，G1 保持 partial。

## 继续：公共头 C++ 包含检查（2026-11-15）

扩展公共头诊断，使用交叉 C++ 编译器及 `-nostdinc++` 检查严格 C++17 模式；发现 `thread_db.h` 依赖未显式声明的 `sigset_t`，已补充声明头。锁定源码干净构建后，诊断性占位头条件下 150 个公共 C 头在 C 和 C++ 模式均可单独包含；对象、补丁和依赖来源验证通过。这不构成线程调试或 C++ 标准库资格。

构建报告 SHA-256 `04155c186b1ca467de47251eea2235f7194784bf183805df1ee31f93aec8ee05`，C++ 扫描 SHA-256 `aee13f41f2d68f1714ce16def9d4aa2ca6faa90bb67004cf383b56a94332cc54`。最终 `gnu/stubs.h`、完整 libc 和可用 SDK 仍缺失，G1 继续为 partial。

## 继续：逐个公共头的传递来源核对（2026-11-15）

公共头扫描现在直接使用报告中散列绑定的交叉编译器及私有 sysroot，记录并校验每个成功编译头的全部传递依赖；仅允许已登记的 sysroot 文件、散列绑定的上游构建期占位头和编译器内置头。扫描前后校验报告、清单、占位头和编译器，C++ 禁用额外 C++ 默认头目录。C 和 C++17 各 150 个公共 C 头通过此诊断，报告 SHA-256 分别为 `63a97b53109d12d68701d66c868d7f7e5435c22d3dbf421fc99438d4f037af8a` 和 `4667f2b4cb9eb554b709b1bd290798d5a3ea97e56b997259d00740d07eac5ec5`。

占位头仅在 sysroot 之外用于诊断；正式 `gnu/stubs.h`、完整 libc 和可用 SDK 仍缺失，G1 保持 partial。

## 继续：恢复随机数桥候选（2026-11-15）

原临时工作树被清理后，恢复 XOS `getrandom` / `getentropy` 候选：使用 syscall 63 的最多 256 字节请求，较长 `getrandom` 返回真实短读；`getentropy` 拒绝超过 256 字节的请求。内核不可用、地址、参数和硬件失败分别返回明确错误，非零 Linux 随机池标志不冒认支持。不据此声称随机源通过密码学质量或发行验收。

宿主模拟覆盖长度、短读、标志和错误；交叉编译的独立目标对象检查 XOS 陷入指令。先前完整 glibc 诊断构建因暂停和临时目录清理未完成，本次隔离 GNU make/gawk/bison 工具也已丢失；真实 glibc 目标构建、客体及最终组合验证均未运行。G1 继续为 partial。

## 继续：恢复隔离工具后的随机数目标构建（2026-11-15）

从本机缓存恢复隔离 GNU make、gawk 和 bison，并修正缺少交叉 `readelf` 所导致的首次配置探测错误；该首次结果未用于验收。重新从候选归档构建后，`getrandom.o` 与 `getentropy.o` 及其源码、补丁、依赖和目标指令检查通过，报告 SHA-256 `1af6afeabe164ba21261e0b9fc3cfd322d3183488e89cb59826c8266555524bc`。完整 libc 仍在 `clone3.h` 处失败；本结果不证明随机源密码学质量或完整 SDK。

新增客体探针路径，使用上述真实 glibc 对象验证短读、上限、标志和地址错误；最终提交后需要重建系统并执行。G1 继续为 partial。

## 继续：固定配置期目标 readelf（2026-11-15）

恢复构建环境时发现，glibc 配置脚本会调用未带目标前缀的 `readelf`；该工具缺失时配置仍可继续，但会错误关闭 x86 ISA 属性探测。探针现显式选择并记录 `x86_64-elf-readelf` 的真实路径，覆盖继承的 `READELF`，验证器检查配置日志与记录一致。

在 PATH 不提供普通 `readelf` 且继承变量故意指向失败程序的条件下，干净配置正确检测到 ISA 属性支持；对象、来源和随机数目标对象验证通过。报告 SHA-256 `93b3e6c4bd324dcbdff7025cc13b1bd14086716da44bea08b3aedda72979d747`。完整构建仍在 `clone3.h` 失败，G1 保持 partial。

## 继续：区分 C++ 前端与目标链接（2026-11-15）

glibc configure 的 C++11/98 探针首先缺少 `<cstdlib>`，目标链接又缺少 crt0、libstdc++、libm 和 libc；不能据此认定语言前端不支持 C++。新增独立的 freestanding C++17 对象探针，禁用 C++ 默认头目录，仅检查 constexpr、模板和 `thread_local` 的目标代码及 TLS 符号；干净构建和对象来源检查通过，报告 SHA-256 `c28f6d53b8195e6e94c68ea547638aed48cc850a234789fafd4d79076d93cfa6`。

该探针不链接或运行，不能证明标准库、异常、TLS 运行时或 C++ SDK 可用；完整 libc 构建仍停在 `clone3.h`，G1 保持 partial。

## 继续：最小静态链接与原生线程入口（2026-11-24）

从锁定归档重跑候选构建。探针屏蔽了调用环境中的头文件、编译器搜索路径、configure site 文件和 make 选项，编译器查询也使用同一环境。以故意设置的 CFLAGS、COMPILER_PATH、CONFIG_SITE、CPATH、LIBRARY_PATH、MAKEFLAGS 和 READELF 验证该路径，配置成功，x86 ISA 属性检测正常。

独立 sysroot 安装了 337 个文件。诊断客户端使用已安装头文件和 sysroot 外的上游构建期占位头，显式链接实际生成的 glibc `abs.o` 与 XOS `_exit.o`。链接映射只包含客户端及这两个对象，目标 ELF 无未定义的命名符号、动态段或解释器。探针记录首个完整构建错误并绑定原始日志，仍为 NPTL `pthread_create` 引入的 `clone3.h`。构建报告 SHA-256 为 `222f3908c7c9e67f806334dbe8f307a41baf53e5124ae1596c35d8c617ff3e29`。

新增 x86-64 原生线程入口，按 SysV ABI 将内核提供的栈和参数交给 C 回调。XOS 会在唤醒 joiner 之前回收 TLS，而 glibc 的 `pthread_t` 使用线程描述符地址。公共 `pthread_create` 接入仍须解决描述符保留、DTV 回收和 join/detach 的生命周期。最终 `gnu/stubs.h` 与完整 SDK 尚未生成。

同批头文件以 C 和 C++17 各编译检查 150 个公开头，全部通过，仍依赖构建期占位头。XOS 镜像 `66f11530e5b7efbc` 的客体报告为 `passed_subset`。真实 `xos_thread_entry.o` 通过回调栈对齐、参数传递、TLS、退出与 join 检查，四轮后资源恢复。调度、PID、时钟和随机数目标对象的组合检查也通过。客体报告 SHA-256 为 `7cffe0c85313ea830a389d8a14bd4f3392192d4a5f128600ab0563dee5f4f4e5`。链接器报告 `getentropy.o` 缺少 `.note.GNU-stack`。

## 继续：原生堆与匿名映射（2026-11-24）

glibc 的 `brk` 接入现有 XOS syscall 29。静态 TLS 引导中的 `_dl_early_allocate` 直接使用这条调用，失败时返回空指针，避免在安装线程指针前访问 TLS 里的 `errno`。宿主测试覆盖返回地址、失败值和堆状态。目标对象的反汇编核实了陷入指令及引导路径无 `%fs` 访问。

`mmap`、`mmap64`、`mprotect`、`munmap` 接入 syscall 67，沿用 XOS SDK 已有的匿名私有映射契约。初始映射仅保留 `PROT_NONE` 地址范围，随后用 `mprotect` 提交和设权。精确映射遇到碰撞返回 `EEXIST`，同时要求写入与执行权限时返回 `EACCES`。默认 glibc 分配器直接请求可写映射的路径仍有兼容工作。

从锁定归档重建后，六个内存接口目标对象的源码、依赖、符号与指令检查通过，逐个构建的 PIC 对象也通过。C 和 C++17 各编译检查 150 个公开头，仍使用构建期占位头。构建报告 SHA-256 为 `2dc89952fda22bf063e301ef41a705eff32f51a2ed5a48ea4ff54842b0299f89`。

镜像 `e728fdec0e012f4d` 的客体探针直接链接这六个对象，验证堆增长、回缩及失败保持原值，匿名地址预留、提交、保护、释放和重新分配后的清零。四轮均通过，资源恢复到 `[129725, 3, 1]`。客体报告 SHA-256 为 `08402b811526375578accc06ab8cad6374c4b88b72134b85f91be2255246232c`。该探针由 XOS 现有 loader 设置 TLS，glibc 自身的主线程 TLS 安装未运行。链接器报告 `munmap.o` 缺少 `.note.GNU-stack`。

并行构建诊断中，上游通用 `mprotect` 与 `munmap` 的别名编译错误已消失。完整构建的第一个错误仍是上游 `pthread_create` 引入的 `clone3.h`。现有内核会在原生 join 返回前回收执行 TCB，静态线程需要让公开句柄与执行 TCB 分离，并明确 DTV 属于线程映射还是独立分配。最终 `gnu/stubs.h` 和完整 SDK 仍未生成，G1 保持 partial。

## 继续：静态线程 DTV 的所有权（2026-11-25）

线程必须在进入 XOS 退出握手前完成用户态清理。新的静态 TLS 初始化入口把 DTV 的三个槽放在执行 TCB 之后，校验对齐和剩余空间。glibc 的实际 TLS 初始化代码只在初始模块为静态可执行文件且代数为零时接受这个 DTV，复用上游的模板复制与清零逻辑。该 DTV 随线程 reservation 一并回收，无需在 join 中读回 TCB 或单独释放数组。普通 glibc 初始化和现有堆分配入口仍使用原路径。

宿主测试覆盖对齐、空间少一字节、模块集合不支持及失败时输出不变。整个线程运行过程中禁止动态加载的策略尚未接入，公共 `pthread_create` 也尚未使用该入口。

从锁定归档重建生成 `elf/dl-tls.o` 与 `nptl/xos_thread_tls.o`。首个完整构建错误仍是 `pthread_create` 引入的 `clone3.h`，正式 `gnu/stubs.h` 仍未生成。构建报告 SHA-256 为 `f137dbd399915190a62299ec8be2053ed94eeae5b29db41b4e68a5ac61919294`。未运行该 DTV 路径的客体验证。

## 继续：静态线程启动与退出（2026-11-25）

新增静态工作线程私有启动入口。它按 glibc 的 TLS 布局计算预留大小，在启动前初始化保留区 DTV、TCB 和栈顶参数记录，再由 x86-64 原生入口调用工作函数。启动失败时可撤销整块预留。回调返回后先执行调用者提供的线程清理，再通过内核退出握手提交完整的 64 位结果。最后一个线程由内核选定，仍可使用本线程 TLS 运行进程收尾回调。

宿主测试验证栈对齐、TLS 初始化失败、启动参数所有权、清理顺序和最后线程分支。锁定归档的目标构建生成 `xos_static_worker.o` 和 `xos_thread_exit.o`，报告 SHA-256 为 `10031dac525e8b3dcf4958d1e1855ea4ff6480fe5a79334124ffcae09b52453f`。镜像 `33c0f47512e22be7` 的客体探针链接实际退出对象，验证 join 保留高位及最后线程成功退出进程，四轮资源回到 `[129725, 3, 1]`。客体报告 SHA-256 为 `96c12d5fc6d33e486fe1a7a60cd2ed16d319ea908412339ae7fcb64774ec650b`。

静态工作线程启动仍只有宿主与目标对象证据。客体探针由原有桥启动，未运行真实的 glibc 静态 DTV、线程析构器或公共 `pthread_create`。完整构建仍停在 `clone3.h`，G1 保持 partial。

## 继续：原生线程身份与回收（2026-11-25）

XOS 后端将 `pthread_self` 和 `thrd_current` 接到 syscall 41，使用完整的 64 位 TID。阻塞 join 和 detach 通过 syscall 44/45，由内核持有回收权，调用方无需访问已经释放的线程描述符。无效截止时间返回 `EINVAL`，有效定时 join 和 tryjoin 返回 `ENOTSUP`。XOS 当前没有原子非阻塞 join 或有截止时间的 join。

主线程的 NPTL TCB 后置初始化也使用 syscall 41，将原生 TID 写入内部 mutex owner 字段，超过该字段范围时明确失败。XOS 分支不注册 Linux robust list 或 rseq。主线程 FS 安装还需要接入，且上游 `pthread_create`、调度、线程属性和信号函数中仍有把公开句柄解引用为 TCB 的路径。该实验后端仍不能作为可运行的 pthread SDK。

从锁定归档的干净构建生成六个相关目标对象，报告 SHA-256 为 `2e35ef7d5ec6205951400642f5b082b32890658a36c3de07cf2472df14bceac2`。镜像 `319b09b87ce6a260` 的客体探针链接身份、阻塞 join 和 detach 对象，验证父子线程的 POSIX/C11 身份与内核 TID 一致、拒绝自 join、保留 64 位结果、拒绝失效 TID 和重复 detach，以及定时 join 明确返回不支持。四轮资源均回到 `[129725, 3, 1]`。报告 SHA-256 为 `6583f693385b3a410946482655592d7e127c0382b590817a3dfaa37c771ec`。真正的 glibc 启动和取消投递未在该客体探针运行。完整构建仍停在 `pthread_create` 的 `clone3.h`，G1 保持 partial。

## 继续：原生 pthread_create（2026-11-25）

静态 `pthread_create` 选择 XOS 后端，经原生线程预留与启动交接 TCB、DTV 和用户入口。公开身份使用内核 TID，内部 mutex owner 字段在启动前检查可表示范围。启动失败撤销预留并回滚线程计数。工作入口为 `pthread_exit` 建立 unwind 返回点，随后依次处理 TLS 析构、TSD 和 libc 线程清理，再由内核选定最后退出者。工作线程从已初始化的静态 glibc 主线程启动，支持内核分配栈、分离状态及继承调度。自定义栈、显式调度和共享 glibc 的线程创建仍不支持。

主线程 FS 安装、仍依赖 TCB 指针的公共扩展接口、动态 DTV 和 glibc 整体链接都有后续工作。客体桥的成功只能验证其实际链接的对象。

干净全量构建按正常规则选中 `sysdeps/xos/pthread_create.c` 并生成 `pthread_create.o`，越过 `clone3.h`。目标对象 SHA-256 为 `dba27379283b01af83b9bb77a3b4f3310cbf87902a07f30fecb2d8a2b13f8f72`。首个编译错误前移到 `pthread_getaffinity.c` 引用的 `__xos_internal_sched_getaffinity`。构建报告 SHA-256 为 `9e5dc9e81356679318c9ad08d5af792cc6f0a99d25f188fb4fe51d1e2bb44ab4`。对象、依赖和陷入指令核验通过，单独的 PIC 对象也完成编译。宿主测试确认预留准备失败不会启动线程，且新线程读取已拷贝的参数。

镜像 `b849999104a49013` 的现有客体桥四轮通过，资源均恢复。客体报告 SHA-256 为 `e6ab3223b3fa9e4c15a2e25f9ebcef92b8e2328963574b7d7447fbf36ee56fc8`。该运行覆盖此前的身份、启动陷入、回收及内存对象。新增公共创建函数仍待完整 glibc 客体验证。最终 `gnu/stubs.h` 与 SDK 尚未生成，G1 保持 partial。

## 继续：线程调度与默认栈（2026-11-25）

XOS 当前不提供线程 CPU affinity、可调的线程调度参数或可跨线程传递的 CPU 时钟 ID。六个相关 pthread 入口按原生契约返回 `ENOTSUP`，保留查询输出，不将公开 TID 解引用为描述符，也不使用 Linux 调用。现有调用者读取本线程 CPU 时间的 `CLOCK_THREAD_CPUTIME_ID` 仍可按原生接口使用。静态 `pthread_create` 改用 glibc 已有的栈属性查询，显式属性未设置栈大小时也读取进程默认值。

从锁定归档的干净全量构建越过 affinity，首个错误移至 `pthread_getname.c` 引入的 `sys/prctl.h`。六个接口的目标对象和 PIC 对象均编译通过，已核验实际选源、符号、错误码和依赖。构建报告 SHA-256 为 `de45db434f6064cd2f76c555f48f7f20bc3014229231c757c89d396646678e03`。镜像 `e95890e0fea5496f` 使用真实目标对象运行四轮，验证错误值和调用方输出不变，并回收资源到 `[129725, 3, 1]`。客体报告 SHA-256 为 `0f95e541339053b1b239186effcd6d11df62c62079c10b343e1fd859aff5e10c`。完整 SDK 和公共 `pthread_create` 的 glibc 客体验证仍未完成，G1 保持 partial。

## 继续：线程名称与初始线程退出（2026-11-25）

`pthread_getname_np` 和 `pthread_setname_np` 使用用户态名称表。表按完整 TID 索引，由原生私有锁保护，容量与内核每进程线程上限一致。创建时继承调用线程的名称，停止前清除记录，启动失败也清除已登记项。名称支持 15 字节加 NUL，缓冲不足或名称过长返回 `ERANGE`，未登记的其他 TID 返回 `ESRCH`。名称仅供本进程 glibc 查询，不设置内核进程名。

初始线程调用 `pthread_exit` 时，glibc 启动代码保存返回值，执行与工作线程同一套清理，再进入 XOS 原生退出握手。这样可把原始返回值交给 joiner，并由内核决定是否执行进程收尾。普通 `main` 返回仍调用进程退出。

宿主测试覆盖名称继承、容量、清空、截断拒绝和失效 TID。从锁定归档的干净构建越过 `sys/prctl.h`，首个错误移到 `pthread_kill.c` 的 Linux gettid 和 tgkill 依赖。新的名称、清理与启动对象均编译并通过来源和调用核验，名称相关 PIC 对象也成功编译。构建报告 SHA-256 为 `9f5c25f94e0be0d4dd0746abd866bc386191550a20173be643b4eb1b9cc0c667`。镜像 `dc00807560875abd` 的既有客体桥四轮通过，资源恢复。客体报告 SHA-256 为 `80b9099b0d29d077b4789d23c106b32df1d5acb840fe70f8ea945fcc7b5596b3`；该桥未调用新的名称 API 或完整 glibc 启动。G1 保持 partial，完整 SDK 尚未生成。

## 继续：原生线程信号接口（2026-11-25）

`pthread_kill` 和 `pthread_sigqueue` 的信号 0 查询使用当前线程的内核 TID 或 libc 已登记的线程记录。工作线程退出清理会移除记录，之后查询返回 `ESRCH`。这条查询不覆盖已结束但仍待 join 的句柄。XOS 尚无异步线程信号投递，非零有效信号返回 `ENOTSUP`。无效信号编号返回 `EINVAL`。

`pthread_sigmask` 对实际掩码变更或读回返回 `ENOTSUP`，保留调用方输出。输入和输出都为空时没有掩码操作，返回成功。内部 raise 接口保留失败，原有 abort 路径仍可执行后备终止。

从锁定归档重跑的干净构建通过线程信号相关对象，首个错误移至 `sem_open.c` 经 `shm-directory.h` 引用的 `NAME_MAX`。目标对象的来源、符号和调用关系通过核验，相关 PIC 对象编译通过。构建报告 SHA-256 为 `20699de4c9163208cf83f667681cf9d56ef6211aafee2fd62b1453855156b3d8`。

镜像 `f8bf7f566380d9bd` 的客体桥链接实际信号和线程名称对象，验证存活登记、失效 TID、非零信号错误、输出掩码不变及跨线程改名。四轮通过，资源均回到 `[129725, 3, 1]`。客体报告 SHA-256 为 `68540e858d801db775e1b3279f151e0993e0abdba45b67f546e6281c4f2f62a0`。完整 SDK 尚未生成，G1 保持 partial。

## 继续：命名信号量和共享内存接口（2026-11-25）

将文件服务的 UTF-8 路径上限导出为 `NAME_MAX=255`、`PATH_MAX=256`。当前 XOS 没有 POSIX 共享对象命名空间。glibc 的 `sem_open`、`sem_unlink`、`shm_open` 与 `shm_unlink` 返回 `ENOSYS` 并保留供上游 `gnu/stubs.h` 生成器读取的标记；`sem_close` 对该后端无法产生的命名句柄返回 `EINVAL`。XOS 构建不选择文件映射辅助对象。私有匿名信号量的实现保留，宿主 `sem_init` 与 `sem_post` 测试通过。

干净构建越过 `sem_open.c`。首个错误移到 `nptl/syscall_cancel.o` 缺少构建规则，探针现把该类 make 诊断计入首错。五个目标对象、PIC 编译、来源和符号检查通过。构建报告 SHA-256 为 `5bd3d0470dd5346c0caa25b0ddac51e3703b3c8fc8cf191ff6ffb1bdc0c67d2d`。镜像 `152cd96f4d4e95ab` 的组合客体桥链接真实目标对象，四轮验证错误码及资源恢复到 `[129725, 3, 1]`。客体报告 SHA-256 为 `5145accfafaeede7076a80b8ef858c295e66878b619383641af96a00c3c519a3`。G1 阶段收尾，正式 `gnu/stubs.h` 与完整 SDK 尚未生成。
