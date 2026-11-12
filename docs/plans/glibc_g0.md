# glibc G0：源码、构建与接口调查

2026-11-12；状态 **partial，未完成源真实性验证和 XOS 后端构建**。目标 glibc 为长期方向；本次不改变默认 libc、现有 ABI 或发行。G0 期间主工作区由 `codex/ports_batch` / `1416c1939382c2fdbbcdc3247c32a20c6b48d529` 切换至 `codex/pthread_header` / `3645a108beb12dcd3fb7c045d25c6609fbc6c561`，后续又切至 `codex/dev_null`；这是并行变化，不将整个工作树声称为单一冻结快照。候选探针与源码归档位于独立的忽略缓存，不占用公共 build。

## 取得的候选源

- glibc 上游官网列 2.44 为稳定版本，发行包主入口为 [GNU FTP](https://ftp.gnu.org/gnu/glibc/)，取得自 [南京大学 GNU 镜像](https://mirrors.nju.edu.cn/gnu/glibc/glibc-2.44.tar.xz)。归档 20,620,544 字节，SHA-256 `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`；`tar -tf` 可读取 21,782 项。该哈希与 [Fossies 索引](https://fossies.org/linux/misc/glibc-2.44.tar.xz/) 一致；这不是上游签名验证。
- 已取得同镜像的 `.sig`，SHA-256 `44aabe605a02a56959bab51b92d985945db66dbd0117debe3d741252b2133ec6`。当前未找到 gpg/gpgv 或经独立渠道确认的可信签名公钥；**签名验证 NOT_RUN**。因此 [候选来源记录](../../src/ports/glibc/source_lock.json) 明确禁止视为正式验证的发行源。任何文件哈希只是本次得到的字节身份，不独立证明发布者身份。
- 上游主源 `ftp.gnu.org`、`ftpmirror.gnu.org` 和 kernel.org 镜像本机 curl 均发生 TLS 连接失败；未绕过 TLS。Google 的 glibc 镜像提供 `upstream/glibc-2.44` 标签对象 `6c33941ff7188ac0813314f249a402a84b1a9d36`、解引用提交 `c3a3a9808ad3ab4a3336836833f83288b672ccbf`。尚未证明该 git 树与发行 tarball 成员逐项一致，也未将镜像标签冒充上游签名。
- 缓存相对路径 `.cache/xos_seed/glibc/2.44/` 包含原 tar、签名、解出的源码和配置探针；缓存不是仓库交付物或 git 信任根。未将 glibc 源码或二进制纳入 XOS 分发。

## 实测构建探针

宿主 Darwin arm64；`x86_64-elf-gcc -dumpmachine` 为 `x86_64-elf`，版本 16.2.0，编译器报告 thread model `single`；交叉 GNU assembler 为 2.47.20260726。普通和线程 SDK manifest 采样均显示 build `d138ffd28415d9c2`，SHA-256 分别为 `12f76d32fc7aa35ad45c99c610c35d1b45a15f8468ca17d854eba14ac74d6634` 和 `bed2716153c1569469b51d1847bfb908a2aa91514a60206bd012430b1e3b1387`；采样不证明其与变动中的工作树完全一致。

从独立 `configure_probe/` 实际执行：

```text
../src/glibc-2.44/configure --build=aarch64-apple-darwin --host=x86_64-unknown-xos CC=x86_64-elf-gcc --disable-werror
```

退出 1：glibc 自带 `scripts/config.sub` 不识别 `x86_64-unknown-xos`。这是最早配置障碍；尚未进入 sysdeps 选择、工具检测、编译或链接，不能声称后面的路径可用。首次用错相对路径的调用退出 127，随后已纠正；该错误不是上游问题。

宿主默认 GNU Make 3.81、Bison 2.3，未在 PATH 找到 `gawk`；[glibc 2.44 工具要求](https://sourceware.org/glibc/manual/2.44/html_node/Tools-for-Compilation.html)列 Make 4.0+、Bison 2.7+、GNU awk。工具版本仅作环境预检；配置尚未进入这些检查。G1 必须以隔离的满足版本要求的宿主工具再次验证，不覆盖机器系统工具或用宿主 libc 充当 XOS 目标。

## 首批接口和依赖矩阵

| 主题 | 2.44 源码证据 | XOS 现状与下一步 |
|---|---|---|
| 系统识别和构建 | `scripts/config.sub` 拒绝 xos；`configure` 有受支持平台检查和 `sysdeps` 选择；`README` 列 Linux/Hurd 配置 | 设计 XOS target、可重放补丁及 sysdeps；需要验证 GCC/binutils 目标与生成器实际组合，不能把 `x86_64-linux-gnu` 强作 XOS。 |
| 线程入口 | `nptl/pthread_create.c` 调 `__clone_internal`，使用 futex；`sysdeps/nptl/libc-lockP.h` 引用 futex | XOS `thread_abi.hpp` 定义 prepare/start/join 和 wait/wake word；二者只有机制上的候选映射，语义/取消/竞态与 glibc 所需 ABI 未验证。不得将 Linux clone/futex 号直接当 XOS ABI。 |
| TLS 与退出 | `sysdeps/x86_64/nptl/tls.h` 包含线程描述符与 `TLS_INIT_TP`；源码 `README` 对 pthread 的 shared libgcc_s 有要求 | 核对 XOS `sys_process_tls`、线程生命周期、FS 基址、TCB、构造/析构和异常/unwind；静态 profile 是否满足要求未测，不能以单线程新库启动代替。 |
| 内存 | `malloc/arena.c` 使用 `mmap(PROT_NONE)` 和 `mprotect`，也有其他分配路径 | XOS newlib 包装仅接受私有匿名及初始 `PROT_NONE` 等受限 profile；VM3 manifest 为 `implemented_unqualified`。匹配地址、权限、提交、释放、失败和并发语义须以客体验证，不能以符号存在证明兼容。 |
| 文件与进程 | glibc 有 `io`、`posix`、`sysdeps/unix` 与目标相关 syscall 路径 | XOS 使用文件服务、loader 和 SDK；清单应逐项覆盖 FD、偏移、CLOEXEC、fork/exec、路径、失败及服务死亡，不将 Linux 策略放进内核。 |
| 网络/信号/动态链接 | glibc 包含 `socket`、`signal`、`elf` 等工作面 | XOS 现有能力与信号、socket、动态装载分别缺口未逐项调查；首个静态探针可限定范围，但不删除最终目标。 |

该矩阵是源码观察与下一步，glibc 头可编译、功能可用、POSIX 合规、XOS 安全/网络支持均 **NOT_RUN**。

## 许可与发行预检

源码顶层有 `COPYING.LIB`、`COPYING.LESSERv2`、`COPYINGv2`、`COPYINGv3`、`LICENSES`；`README` 指向 `COPYING.LIB`。`LICENSES` 说明部分第三方版权声明须随相关二进制分发。按实际选入源文件、配置、对象和许可证例外建立材料与逐成员映射；静态发行应评估对应源码、修改和可重链接材料。当前未进行逐文件/成员审计、法律判断或发行资格检查。

## 下一步与关闭条件

1. 取得可信签名工具并通过独立渠道确认发行签名公钥后，校验已有 `.sig` 与 tar；失败时保留失败记录，不把候选锁升级为正式锁。签名通过仍需绑定源码、补丁和构建输入。
2. 在独立工作区准备符合版本的 GNU make、gawk、bison；提出并审查 XOS 目标识别与 sysdeps 的最小补丁，重跑真正的配置并记录系统路径选择，继续到下一个真实阻塞。涉及系统机制另按 [移植期纪律](../Discipline.md) 与 C20 协调。
3. 扩展矩阵至启动栈、辅助向量、符号、线程描述符、可执行/匿名映射及失败语义；为 G1/G2 设计实际链接和客体测试，不把这次配置失败当移植进度通过。
4. 本次未建立正式 XOS 工具链或 glibc SDK，未对 glibc 做交叉编译、链接、客体、应用兼容或许可完整验收。G0 保持 partial；不妨碍在独立目录继续 G1 所需的目标识别和工具准备。
