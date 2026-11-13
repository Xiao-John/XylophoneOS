<!-- coderabbit-ai-generated:v1 -->

# popen 父端 CLOEXEC 评审修复

2026-11-13，基线 `d37aaf1a734412970c968322408c522fcb99b895`。

确认问题仍存在：本次 spawn 的 close 动作不会保护后续 spawn。修改
`src/user/libc/process_posix.cpp`，在 fdopen / spawn 前为 parent_fd 设置
FD_CLOEXEC；失败保存 errno、关闭两端、释放槽位并返回空指针。
既有 ABI 不变；调用者保留管道流，后续子进程不再继承父端描述符。

## 验证

宿主 g++ 15.2.0，系统 libc 与 /bin/sh，临时包装测试通过：读写模式、
后续 system 子进程不继承父端、80 次 fcntl 失败均无 spawn、两端关闭及槽位复用。
编译命令以仓库为工作目录：

```sh
g++ -std=c++20 -Wall -Wextra -Werror -Wno-nonnull-compare -c src/user/libc/process_posix.cpp -o /tmp/process_posix.o && objcopy --redefine-sym system=xos_system --redefine-sym popen=xos_popen --redefine-sym pclose=xos_pclose /tmp/process_posix.o && g++ -std=c++20 -Wall -Wextra -Werror /tmp/popen_cloexec_test.cpp /tmp/process_posix.o -Wl,--wrap=pipe,--wrap=fcntl,--wrap=posix_spawn -o /tmp/popen_cloexec_test && /tmp/popen_cloexec_test
```

临时测试不入库；objcopy 仅重命名宿主测试对象符号以避免调用系统 libc 的同名实现。
`-Wno-nonnull-compare` 用于宿主 glibc pclose 声明与现有空指针检查的差异。
首次宏重命名编译因宿主 cstdlib 的 system 声明失败，首次直接编译因上述
nonnull 警告失败；最终命令通过，均未因此修改产品代码。

客体 `tests/posix_shell_guest.py` 未运行：缺少 x86_64-elf 工具链、NASM、
build/manifest.json 和 build/sdk。下一步在准备好的构建环境重建 SDK 并运行该客体测试；
宿主通过不能替代 XOS 客体资格。
