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
