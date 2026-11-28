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
