# 5b6c6dff · glibc CPython G4 首个客体切片

从正常系统源码 `6dcf7fb4` 独立构建。使用项目锁定的 CPython 3.14.9，
先核对源码摘要再构建同版本的 Linux 宿主解释器。复用已验收终端就绪的
glibc 2.44 C SDK，采用现有签名证据和 profile 准入核对整个 sysroot、
静态库、CRT 与交叉工具。目标为 `x86_64-unknown-xos`。
构建最多使用两个作业。

## 真实构建与修复

现有 CPython 入口调用 `--sdk` 时使用 newlib 的 `include`、`lib`、
`crt0_posix.o` 布局。传入 glibc 候选时，首次失败是 C++ 时间桥找不到
`xos/sdk.hpp`。本轮独立驱动使用 glibc sysroot、原生接口头和静态启动对象，
从固定 CPython 源码应用现有补丁。该驱动跑通真正的交叉 configure，
构建保留原生 pthread 并选择 `dynload_stub.o`。正式 CPython 构建入口的
glibc 选项仍是独立的交付工作。

第一次编译时间模块暴露两个 newlib 假设。glibc `clockid_t` 是有符号
`int`，旧 XOS 分支使用 `unsigned long`，触发上游大小断言。签名 SDK
提供真正的 `clock_gettime` 和 `clock_getres`，传统 `clock` 仍为
ENOSYS，旧代码却无条件调用最终回退。应用补丁选择正确的时钟 ID 类型，
只在 configure 确认可用时编译 `clock` 回退。复编的两份目标对象通过，
时间模块符号检查显示使用 `clock_gettime`、`clock_getres`。

完整目标编译随后在链接阶段发现 legacy `times` 弱包装仍引用 `_times`。
将该包装限制在非 glibc 路径后，静态 CPython ELF 链接成功。ELF 有
`PT_TLS`，没有动态解释器。链接仍如实警告当前 `raise`、
`clock_settime`、`execve`、`times` 和 `fchmodat` 不可用。
另有一份原生 newlib SDK 对照将补丁前后时间桥编译为逐字节相同的目标对象。
在同一真实 newlib 时间头文件及既有时钟配置下，两个受影响的 CPython
函数的预处理结果也逐字节一致。既有时间桥宿主测试通过。

## 客体验收

QEMU 11.1.3 在私有 FAT32 盘上通过正常 `exec-file` 启动实际解释器。
库文件仅放入固定源树的 `os.py` 和编码包。在原生 XOS 上验证
CPython 3.14.9 启动、进程 CPU 时钟与分辨率、单调时钟和阻塞休眠、
一个实际 `_thread` 工作线程及其线程 CPU 时钟。进程退出 0，
前后均为 129795 空闲页、2 个任务、0 个完成记录。Pillow、扩展包、
动态加载、交互 REPL 与全量标准库属于后续验收。

| 输入与回执 | SHA-256 |
| --- | --- |
| CPython 3.14.9 源码包 | `e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53` |
| 已核验 glibc C SDK manifest | `1a433be76f4a6193de70453f595f06298449f46ecdd4604c4a8c4e9d134028e8` |
| 目标 configure 成功、时间模块失败回执 | `274f8eb20a7a4076d76915d8bd54a790b1661227f2f42ad2fa6fc0dec54dca` |
| 时钟修复后对象通过、旧包装链接失败回执 | `2e02438fdaf7ad8528ebfa968bce9e5d168868ed2916faab5bb21e872fba9eca` |
| glibc 静态解释器 ELF | `b6bb7c24a3bc3605a95ec54bbaf45cc32653316e4e715f4aba64fe7c3b659b70` |
| 正常系统 `76ac3673fa701ccf` ISO | `ea06be40c1db2148f9fd65c43a811b4e4219166e431108dc43758e2ed9ee06eb` |
| 客体运行回执 | `72e2ac2c7153235718c5310621315812d6b743671db21a932baa649a87abc123` |

[CPython 源码锁](../../src/ports/cpython/source_lock.json) ·
[时钟兼容补丁](../../src/ports/cpython/patches/0007_glibc_clock_types.patch) ·
[时间桥](../../src/ports/cpython/xos_time.cpp)
