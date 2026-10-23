# 给朋友的 XOS 用户程序快速开始

## 现状

可以写用户态程序，但**不是“在 XOS 里写代码然后按编译”**。当前流程仍是：

> 宿主写代码 → 用 XOS SDK 交叉编译 → 加进启动镜像 → 在 `sup>` 用 `exec` 运行。

E06 已接入 newlib：C 程序可以用 `printf`、`malloc`、`strcpy` 等；E07 的工作盘
负责持久保存文件。但 XOS 内还没有 GCC/G++（E08），也没有完整 POSIX 文件路径、
libstdc++ 或 C++ 静态构造。

## 先跑现成例子

```sh
make disk    # 第一次；已有 work_disk.img 时不会覆盖
make build
make run
```

```text
xos64> run
（约 1 秒后旧演示任务自动停止）
sup> exec libc_hello
```

预期：

```text
libc says: malloc+printf 42 beef
second line
kind=exited code=7
```

## 加一个窄 SDK 程序

不需要 libc 的小程序：

`src/user/programs/hello_friend.cpp`：

```cpp
#include <xos/sdk.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("hello from my friend\n");
    return 0;
}
```

在 `scripts/user_build.py` 的 `names` 中加 `"hello_friend"`：

```python
names = ("supervisor", "files", "demo", "fault", "spin", "slow",
         "echo", "hello", "libc_hello", "hello_friend")
```

```sh
make build
# 关掉旧 QEMU，再重新 make run
```

```text
xos64> run
sup> images
sup> exec hello_friend
```

`images` 应出现 `image=hello_friend`；程序结束回到 `sup>`。

## 加一个 libc 程序

C 库程序除了加入 `names`，还要加入 `libc_programs`：

`src/user/programs/libc_myapp.cpp`：

```cpp
#include <xos/sdk.hpp>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" int xos_user_main(const xos::startup_info*) {
    char* text = static_cast<char*>(malloc(32));
    if (text == nullptr) { printf("malloc failed\n"); return 1; }
    strcpy(text, "malloc+printf");
    printf("libc says: %s %d %x\n", text, 42, 0xbeef);
    free(text);
    puts("second line");
    return 0;
}
```

```python
names = (..., "libc_myapp")
libc_programs = ("libc_hello", "libc_myapp")
```

然后 `make build`、重启 QEMU、`run`，在 `sup>` 执行：

```text
sup> exec libc_myapp
```

限制：进程私有静态堆只有 64 KiB；`fopen`/`open` 路径没有接到 XOS 文件服务，
会返回 ENOSYS。

## 能做什么

| 现在可以 | 现在不行 |
|---|---|
| 静态 ELF64 用户程序 | 原生 GCC/G++（E08） |
| `xos::sdk` 的 print/read/write/进程/IPC | 动态链接、`dlopen` |
| newlib 的 printf/malloc/string/exit | 完整 POSIX、`fopen`、目录/路径 |
| `exec` 启动镜像里的程序 | `std::string`、libstdc++、异常/RTTI |
| `exec-file` 运行工作盘上已有 ELF | 宿主自动安装 ELF 到工作盘的工具 |
| 文件命令、保存、`sync`、重启保留 | 完整 shell、作业控制、多客户端文件服务 |

- 程序镜像上限 128 KiB（strip 后），每任务最多 64 个用户页。
- argv 最多 8 项（含程序名），每项最多 63 字节。
- 工作盘先由宿主 `make disk` 显式创建；`make smoke` 用临时盘，不写日常盘。

## 常见错误

- `exec: unknown image`：程序名没加进 `names`；构建后自动进入 catalog。
- `exec: error=-2`：ELF 超过 128 KiB 或 ELF/段布局不合法。
- 程序刚启动就 fault / `#UD`：可能是旧镜像，或 libc 程序忘了加
  `libc_programs`；重新 `make build` 并关掉旧 QEMU。
- QEMU 报 `Failed to get "write" lock`：旧 QEMU 还在占用 `work_disk.img`，
  先退出旧实例。
- `fopen`/`open` 返回 ENOSYS：当前 libc 没有 POSIX 文件路径，这是预期边界。

## 下一步

E08 才把原生 GCC/G++ 搬进 XOS；到那时才谈“系统内编译”。E09 才做完整的
编辑—保存—编译—运行试用。

更完整的机制见 [E04 SDK](e04_loader_sdk.md)、[E06 libc](e06_libc.md)、
[E05 文件服务](e05_file_service.md)、[E07 工作盘](e07_persistent_work_disk.md)。
