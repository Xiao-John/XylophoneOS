# 2ba757e4 · glibc D1 原生 auxv 消费验证

2026-11-26 · 基线 `142f25dc`，探针 `7b882c7c`。使用同一份已验签的 glibc 2.44 静态 C++ SDK、历史 XOS ISO 和两个锁定的 ELF 输入。实际运行 glibc `elf/dl-support.c` 的 `_dl_aux_init`，该函数选用 XOS `sysdeps/xos/dl-parse_auxv.h`。 [启动栈证据](51852664_glibc_d1_private_entry_stack.md)

静态探针在真实 v2 进程中构造两份含原生熵的初始栈，切换 `%rsp` 后，将参数和环境末端的同一 auxv 交给 `_dl_aux_init`。检查了 `_dl_phdr`、`_dl_phnum`、页大小、随机存储指针和 ordinary/secure 两种内部状态。`getauxval` 按实际 glibc 入口读回每个已生成的标准键，包含指向两个已映射映像的 `AT_PHDR` 和 `AT_BASE`。每轮恢复静态程序原有的 auxv、随机指针和 secure 状态。正常退出 0，资源前后均为 `129711 / 3 / 1`。

这个已存在的解码器要求调用方先提供安全可读、以 `AT_NULL` 终止的数据。XOS `_dl_parse_auxv` 写入普通值表时连续读取到终止项。同键出现多次时后值覆盖前值，而 `getauxval` 的原始表扫描返回最早值。启动桥须先验证段内范围、长度、唯一键、必需值和已批准的未知键策略。静态 `_dl_aux_init` 在 `AT_PHDR` 缺失时回退到自己的 `__ehdr_start`，动态解释器必须检查 main PHDR 的真实映像来源和装载偏移。此次调用发生在已初始化的静态测试进程内。证据覆盖同一布局的真实 glibc 消费，未验证共享 `_dl_sysdep_start`、早期文件访问或解释器启动。

## 两个私有方案影响

| 方案 | 改动与边界 |
| --- | --- |
| 原生 x86-64 glibc 入口保持现状，使用受信 bootstrap 的独立只读映射 | 保持 `%rsp`、`_dl_start(void *)`、`_dl_start_user` 和主程序 `%rdx` 语义。需规定私有映射的发现方式、版本和生命周期，并证明构造时在现有拥有者权限范围。若用新 auxv 键带指针，`_dl_auxv` 会保留该键，普通 `getauxval` 可以读到它，需先约定是否从公开表剔除及何时撤销描述映射。独立私有定位方式可保留本轮标准 auxv 集合。 |
| XOS 增加私有解释器入口，独立参数携带只读描述指针 | 需提供 XOS `RTLD_START` 和内部 C 转交路径。`%rdi` 已用于原栈，额外寄存器须由新入口显式保存并转发，现有 `_dl_start(void *)` 不提供第二参数。自重定位前的保存须避免依赖普通 GOT、TLS 和 libc。主程序看到的初始栈与 `%rdx` 回调约定可以沿用。 |

两者都需要单独设计原生授权、引用交接、文件会话连续性和 ready/error。已有 startup v1/v2/v3 的保留字段、普通应用的环境变量与当前内核 ABI 均不用于这两个方案的选择。当前探针未使用新 auxv 键、寄存器约定或启动 wire。

按上一轮命令使用已冻结的 `main-pie.elf`、`interpreter-fixture.so`、ISO 和 C++ SDK profile，再额外传入 `--define D1_AUXV_CONSUMER`。运行标准 `exec-file`，检查 `D1_GLIBC_AUXV_PASS native_decoder=static ordinary=ok secure=ok`。QEMU 11.1.3，单 CPU、512 MiB、无网络。

| `build/handoff-evidence/` 工件 | SHA-256 |
| --- | --- |
| `entry-stack-auxv.elf` | `3a6590922357ef3de7f4b1860ff7fbddc4e5458ec6385f5aabadc3e278d9275a` |
| `entry-stack-auxv.elf.build/manifest.json` | `f1ce0953fb519bb5b6ce157b702451a32e3da82a6fed74f121b4819f8cdfe697` |
| `guest-report.json` | `6d92617c42f47ea38ff9edb228c16f5c0f46e20ad737ce25b5d2bba3d48ba439` |
| `entry_stack_serial.log` | `882cb94334811e7c250d78301b63a7bd7d1e7270af66a94e625d3057f957ace8` |
| `glibc-symbols.log` | `7c43afc830543a692631e66f78e24dbe27aefdf1fa523d8025e7fd810bc3548f` |
