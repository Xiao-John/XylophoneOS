# P0 R2 闭包与激活控制器恢复

恢复工作接续新的启动控制器资格 `6c1ded23`。本模块没有沿用丢失环境的闭包
产物或测试结果。它与公共 runtime 模块的 `dynamic_elf.hpp` / ELF 检查器、
capsule、bootstrap 和 GNU rtld 配套；源代码 checkpoint 不单独宣称完整
动态程序启动已通过。

## 源码 checkpoint

- 一次性配置可信根与继承的 sequence/revoked 状态，当前根完整预检后发布。
- 实际 readonly pin、fstat、完整 SHA-256、身份、ELF/版本预检；同一句柄留给映射。
- 一个有限绝对期限和每个 pin 的有界缓存；manifest 预算只缩短期限。
- verify-all-before-commit 的 active 切换和显式批准根回滚；当前 admission 撤销检查。
- manifest/object token 只有 acknowledged close 后清除；未知结果保留所有权并 quarantine。
- 原生 C++ basename `+` 和早期 heap 避让。

Preview 2 内严格 PIC freestanding 目标编译通过（GCC 16.2.0，Wall/Wextra/
Werror/Wconversion/Wshadow）。本 checkpoint 的新增 orchestration host、
sanitizer、公共 GNU native guest 资格仍为 **not_run**，后续补充实际结果。
协议细节见 [闭包契约](../contracts/dynamic_closure.md)。

## 新的组合 host 资格

2026-11-28，测试 checkpoint `302161d3` 在 Preview 2 完成 21 个独立进程
案例，每例普通与 ASan/UBSan 各运行一次，共 **42/42 通过**。生产 closure、
SHA-256/generation、静态 ELF 和公共动态 ELF 检查器均直接链接，只有 Files
传输替换为保留不可变 OFD 快照的模型。输入是 SDK 真正编译/链接的 bootstrap、
interpreter、PIE main 与带 TLS/版本符号的共享库，不是手填 ELF header。

结果覆盖当前批准根、SDK 不匹配、不可变 pin/命名空间替换、清理准确一次、
未知 open/read/close 的 quarantine、不重放与不复用、一个绝对期限、完整
预检后激活、过时更新、回滚、撤销 active 和恢复另一个批准根。附加的七类
元数据负例先重新批准修改后文件的摘要，再确认 NEEDED、SONAME、W+X、缺失
RELRO、非法 relocation 目标、TLS 对齐和 version hash 仍被实际解析器拒绝；
所以不是只靠摘要不符得到失败。

这套真实链接输入发现并推动修复了无导出符号 PIE 的空 GNU hash 表检查。
资格绑定公共 parser 修复 `dd698dfa`（在本树为 `312d21b9`）、闭包修复
`6006225b` 和测试 checkpoint。closure hash 为
`1883c142f0c2af102adf02f16b155fbf27220f4ac83d8bf702030228e234e6c8`。
详细输入、命令、工具身份、每次结果与日志在
[R2 host 报告](../reports/dynamic_closure_recovery_20261128/README.md)。

本报告的 guest 字段仍为 **not_run**。它提供闭包/激活/清理层的组合验证；
公共 GNU libc/libstdc++、真实 Files pin 转移和 bootstrap/rtld 的最终原生
guest 资格由公共 runtime 模块另行给出，不把 host 结果替代成客体运行。

## 公共 C++ 性能修复后的新 host 资格

真实 libstdc++ 的 6349 个动态符号暴露单个 pin 缓存跨 symbol/string/version
表交替读取的成本；公共 runtime agent 的 `7287757c` 将三个有界元数据表改为
顺序预检。只增加局部 4 KiB buffer，不扩大绝对启动期限，不改变 pin ABI。
导入为 `47e5ab91` 后，原有真实 ELF/闭包 host 21 例普通及 sanitizer 全部重新
运行，**新的 42/42 通过**，包含七类重新批准摘要后的 ELF 语义负例。

新报告在 [顺序预检资格](../reports/dynamic_closure_sequential_20261128/README.md)。
旧报告继续只指向旧字节；新的 native SDK、GNU libc/libstdc++ 和 R2 guest
仍须分别绑定新产物重建、运行，不能用这个 host 结论替代。
