# 自研内核的受限 C++ 初稿

E01 实施规则，2026-10-23。只约束自研内核与相应底层组件，未来移植的
GCC、libstdc++ 或用户应用按各自运行环境处理。当前使用 C++20。

允许类、enum class、constexpr、适量模板、引用和正常作用域中的 RAII。
表达资源与尺寸不变量，避免为当前小功能引入通用框架。

当前不支持异常、RTTI、TLS、全局动态构造或需要 guard 的局部动态静态初始化。
启用 `-fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit`；
关闭线程安全静态初始化不代表动态初始化已经安全，当前只允许常量初始化。
链接产物检查 `.init_array/.fini_array/.tdata/.tbss`，出现即失败。

当前没有通用堆分配器；new/delete 和隐式动态分配仍不可用。E02 的物理页分配器
只按 4 KiB 页显式分配并返回错误，不假定分配总成功；内核自身对象仍为静态存储。
后续显式分配器须定义失败、对齐、可用上下文、所有者与退出回收语义后再使用。
当前虚函数没有实际需求；引入时审查 vtable、纯虚辅助函数与对象生命周期，
不要求所有上游应用都禁用虚函数。

当前不链接 libc、libstdc++ 或 libgcc。E04 实际产生的 memset 由
`src/shared/runtime/memory.cpp` 真实实现，volatile 写防止优化成自调用。
基础整型来自共享 abi_types.hpp，内核 types.hpp 转引并检查宽度。链接必须无未解释外部符号；未来确实生成辅助调用时，
接入已审计运行库或真实实现，不能填返回成功的假函数。
`freestanding` 不自动保证没有运行库调用，最终仍检查符号和反汇编。

通用编译选项在 `scripts/toolchain.py` 的 `COMMON_FLAGS`。
x86-64 专用选项单列为 `X86_FLAGS`：基线 `-march=x86-64 -mtune=generic`，
低地址 small code model、禁 red zone、只生成通用寄存器代码。
当前内核不使用 FP/SIMD；E06 已实现用户任务 FXSAVE/FXRSTOR 保存，实际反汇编继续检查内核生成代码。
使用 FP/SIMD 或切换任务前必须重新审计并落实保存机制。

内核入口使用 System V AMD64 函数约定，调用前栈 16 字节对齐，清方向标志，
清零 BSS，提供 16 KiB 启动栈。E03 起 ring3 开 IRQ0/PIT 抢占，内核入口仍关中断。
异常帧使用固定缓冲；ring0 panic，ring3 终止任务并回收。RAII 只处理
正常控制流，不能当作崩溃恢复。异常入口和触发代码放在 `arch/x86_64/`，通用
`panic`/控制台不含内联汇编。
DWARF 调试信息与帧指针保留，不将 `.debug_frame` 误认为异常展开运行库。

参考：[GCC freestanding](https://gcc.gnu.org/onlinedocs/gcc/C-Dialect-Options.html)、
[GCC x86 options](https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html)。
这些选项的最终组合以 manifest 和实际 ELF 为证据。

## 用户程序（E03）

当前 ring3 演示程序是 `src/user/demo/*.asm` 的 NASM 平铺二进制，经构建脚本
嵌入内核；它们不是受限 C++ 规则的对象，也没有 libc/libstdc++。系统调用 ABI
是 RAX 编号、RDI/RSI/RDX 参数、负数错误；用户指针由内核先验证再复制。
E04 提供最小 CRT、SDK 和静态 ELF 程序，尚非完整用户 C/C++ 环境。当前 SDK
暂使用整数寄存器配置，CR0.EM/TS 使手写 x87 触发任务异常；未来支持 FP/SIMD
必须先实现上下文保存，不能只删编译选项。中断入口 cld 后才进入 C++，避免用户
DF 影响内核。详见 `e04_loader_sdk.md`；这不是对未来移植应用的永久语言限制。

## 用户态最新边界（0021，2026-10-24）

上面的E03整数寄存器/无libc段是当时历史，不覆盖当前用户态运行环境；内核限制
仍不变。用户态已有newlib、FP/SIMD保存、ctors/fini、静态local-exec TLS及正常
exit的非平凡TLS析构（main return/显式exit已验）。C Seed已验收，目标G++/标准库/
throw-catch/RTTI仍待E08-5真实gate，不能把内核禁用标志应用到移植的C++程序。
