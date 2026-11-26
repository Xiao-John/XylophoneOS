# 4f844926 · glibc D1 解释器入口准备

基线为已合入的[私有文件会话交接](0aa96e34_glibc_d1_early_files_session.md)。
本次实现将原生 LOAD 映射、私有 auxv 栈和同一进程内的 G3 文件会话组合
到实际 loader 归档。它从已核验
闭包提供的两个只读 pin 和预算映射 main 与解释器，检查从 pin 复制出来的真实
ELF 头、入口地址和 main 的 `PT_PHDR`。在两个映像、栈和会话都准备完成后，
原持有方把已认证会话移到私有启动记录；调用方继续持有本次映射、私有 pin 的
关闭责任和启动决定。第二个映像或后续准备失败时尝试撤回两个映像。任何未成功
撤回的原生错误须由 bootstrap 终止处理。

记录位于现有容量有界的初始栈之后。该位置从原始 `%rsp` 计算，避开初始
`argc/argv/envp/auxv` 和向下使用的栈空间。共享的内部 C/C++ 定义配有原生栈
范围和容量检查。记录未增加公开系统调用、通道消息、进程记录或 auxv 键。
在单一启动线程中，完成方还可以用记录内的会话关闭已复制的 pin。随后该记录的
同一会话由后续阶段接手；原来的持有方不能再发送。

## glibc 2.44 接入位置

- `sysdeps/x86_64/dl-machine.h:136` 的真实 `_start` 将同一原始 `%rsp` 交给
  `_dl_start`。后者依据实际解释器映像和动态表自重定位，在
  `elf/rtld.c:494` 调用 `_dl_sysdep_start(arg, &dl_main)`。
- [入口检查器](../../src/ports/glibc/sysdeps/xos/xos_rtld_entry.c) 准备在自重定位后
  接收这同一地址。它核对记录版本、有界 argv/envp、确切的必需 auxv 序列、实际
  PHDR/ENTRY/BASE 的交接值及 `AT_RANDOM` 存储位置，返回供 XOS 启动后端消费的
  视图。真实 GNU `elf` 构建规则以 `-fPIC -DSHARED -DMODULE_NAME=rtld`
  产出该对象；没有未定义符号或 TLS 重定位。
- `_dl_sysdep_start` 还须设置 glibc 启动全局状态，在调用 `dl_main` 前让 rtld
  早期文件操作可用并遵从动态入口的原生错误协议。现有
  `dl-load.c:1309` 与 `dl-map-segments.h` 会调用文件支持的 `__mmap`；
  XOS 通用 `mmap` 只提供匿名私有保留。闭包加载需要复用原生映射机制，
  并在 rtld 与后续 libc 之间明确同一文件会话的持有和移交。启动总时限、
  认证 ready 与提交后错误通知也属于完整入口契约。
- 原生启动守卫继续启用。精确签名源构建生成上游要求的 CSU 头之后，
  `make ... elf/ld.so` 首个错误是 `sysdeps/xos/dl-sysdep.c:5` 的既有守卫。
  真实 `rtld.os` 和 XOS 入口检查器都已编译；完整共享解释器未链接或执行。

## 可重放的验收

用验签 GNU glibc 2.44、GCC 16.2.0 和 GNU binutils 2.47 重建 C SDK 和
`stdio_transfer` profile。受测系统与测试的构建输入和公开提交
`ddbd18dac9047f7452383abb350caf73e540508c` 一致。两份树之间只有前序工作日志
的文字差异。在 x86-64 QEMU
11.1.3，真实 dash 将 FAT 文件重定向为子进程的 stdin。探针在真实静态 CRT
开始前，用同一认证会话开两个 FAT pin，核对各自 SHA-256，完成实际 VM
映射，从映像中核对 ELF 头和入口。新映像来自实际 GCC PIC 和 GNU ld，
包含一个带 XOS `PT_INTERP` 的 PIE 与一个 `ET_DYN` 测试输入。

探针先验证解释器预算不足时撤回 main，再验证 PHDR 数不匹配时撤回两者。
之后同地址准备成功，main 的表有 8 项，解释器输入入口是 `0x180040002000`。
用构造出的 `%rsp` 调用真实构建的共享入口检查器；两个输入都保留为映射数据。
关闭两个私有 pin 后，实际 G3 接手原会话。真正的静态 glibc 运行
`_dl_aux_init` 并用 `getauxval` 读回 PHDR/PHNUM/ENTRY/BASE。晚期
`read(0)` 在早期读完 `ABCD` 后继续读到 `EFGH`，接下来的 ping 请求为
63，早期持有方最后一个请求为 61。子进程和 dash 都退出 0，空闲页、任务和
完成记录保持 `129696 / 3 / 1`。这是入口准备的真实原生证据。

原生 mapper 客体回归和当前公开 ABI 登记一致性通过。原私有栈宿主 UBSan
测试使用它原先的两个初始 ELF，覆盖三种原生 startup、三次实际栈切换、
64+64 容量和 11 项拒绝。第一次客体构建暴露生成的 C++ 计划头包含顺序错误，
随后从提交后的精确源码重建系统和客体并通过。

| 工件 | SHA-256 |
| --- | --- |
| 验签记录 | `11b1ab152735e4842acc6e8857f89c1c6be735fd227292c561c17143fa55539c` |
| C SDK manifest | `496823f2a377fef17e3ae6dbe77ec20e07959d8e5507e6c16972bc4aa0257ff5` |
| stdio profile | `e16f2b2c2fca37b3431fdb151a00c7298a768308e160fd1c3b32e5b84ca3c8a1` |
| 系统 ISO `8a5afc83fc1bc6f1` | `6b892393d9ee8f58d30b11349ee9be6502938d7c2da25b075cd8ba0c90ad1b38` |
| GNU `rtld.os` | `928f6af32b0f7a711d0c7ef983f935a4336caca8b6147fc48cde474460ac4d89` |
| XOS `xos_rtld_entry.os` | `3d9f5bbb79c75b042ac0570a048ea71a0a6c9da1c730cdfb96702bedfcab5991` |
| 客体 ELF | `9322779eade7a3bf981672dbeeba6203734661e06da92082f52b6d628904e6e3` |
| 客体回执 | `28901488014ca533058ec370361557de195386fed3c78840c8a963d0c600ab1f` |
