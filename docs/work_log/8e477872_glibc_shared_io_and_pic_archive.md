# glibc 内部 I/O 符号与 PIC 归档

共享构建基线为 `6f10bd7d`，已有 x86 符号版本基线以及 `open`
和 `ttyname_r` 的内部别名。glibc 2.44 上游发行包从签名验证开始准备，
归档 SHA-256 为 `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`。

- 为 XOS 的 `unlink`、`isatty`、`tcdrain`、`tcflush`、`fsync`、
  `ftruncate` 和 `ftruncate64` 配齐内部声明与定义。共享 `fsync` 也需要
  `libc_hidden_weak (fsync)`，以保留其默认可见的弱别名。
- 通用 `setsockopt` 存根补上与内部声明配对的隐藏定义，仍返回 `ENOSYS`。
- POSIX fatal writer 直接包含 `errno.h`，以编译其已有的错误重试检查。

## 构建与核验

在包含 GNU Make 和 `x86_64-elf` 交叉工具的 Linux 构建环境中准备候选树。
令 `source` 指向签名验证后完成补丁应用的源码，`shared` 指向共享构建目录，
`static` 指向同一次准备生成的静态构建目录。对上述八个 I/O 对象执行 GNU
Make 的实际目标，分别用静态基线和候选运行后两步。

```sh
python3 scripts/probe_glibc_rtld.py --archive "$archive" --output "$out" --jobs 1
source="$out/prepared/glibc-2.44"
shared="$out/shared"
static="$out/prepared/configure"
make -j1 -C "$source/$subdir" "objdir=$shared" "$shared/$subdir/$name.os"
x86_64-elf-readelf -hWs "$shared/$subdir/$name.os"
make -j1 -C "$source/$subdir" "objdir=$static" "$static/$subdir/$name.o"
x86_64-elf-objcopy -O binary --only-section=.text "$static/$subdir/$name.o" "$name.text"
```

八个共享对象均含全局隐藏的 `__GI___*` 内部符号和默认可见的公开弱符号。
八个静态对象的 `.text` 与基线逐字节相同。候选准备清单 SHA-256 为
`7c9bd2b008d7ecb7aa01f26c4652dffcee9cb626e2fcdb33003869eb0a96f190`，
签名验证报告 SHA-256 为
`6e8f0e7b57837e7442e8995c19022f32716e292919d9bda8d687644fedfe9133`。

用两次已签名的准备清单核对一致的上游源码与全部输入。仅把上述八个已核对的源码变动
带入保留的共享构建目录，然后执行 `make -k -j1 -C "$shared" "$shared/libc_pic.a"`。
GNU Make 实际生成了 `libc_pic.a`。其 1,645 个成员与 44 个 `stamp.os` 记录的
构建输入按重数逐项一致。GNU 构建还生成了全归档部分链接产物 `libc_pic.os`，
ELF 类型为 x86-64 `ET_REL`。部分链接记录了 `cpu-tunables.os` 缺少
`.note.GNU-stack` 的警告，后续最终解释器和共享库须验证栈与段保护。

| 产物或记录 | SHA-256 |
| --- | --- |
| 共享归档 `libc_pic.a` | `a0045f4872c0fafc95c75d06e3cf2d1572283838366cae1a5093025acfbb4cb3` |
| 部分链接对象 `libc_pic.os` | `64e6b9cc27a855ed9aeb18dbde6a77ae2ffdf51b7da61b375abd4faa59b7a27d` |
| 归档成员核对 | `205def999ce207259d4fea26b7926f9ed713946760621e0a2df0d2425e553164` |
| 构建输入变更核对 | `3c527e4d6bb60377ea43dee83fd1d9bf785e37d817476670d9864aab48165af2` |
| GNU Make 归档构建日志 | `88bdd0f2fcf1af9ef2569f39f66963afee8efeaa351c7ac7fb3a4e7005a6aede` |
| 补头文件后重建的 `elf/static-stubs.o` | `08c3c1c43c57c198a119c7b671426ba83c19ea933b08dacbae792ec9d7cf0cff` |
| 单独请求 `elf/ld.so` 的失败日志 | `9b2ab60d75b7ed61766318a383af8f731182c48629d5454d034d07abc0542219` |

最初请求归档时，GNU Make 同时报告 POSIX fatal writer 缺少 `errno.h` 和
XOS 解释器启动保护。应用头文件补丁后，单独重建 `elf/static-stubs.o` 成功。
再次请求 `libc_pic.a` 返回 0，Make 判定已有归档为最新。单独执行
`make -j1 -C "$source/elf" "objdir=$shared" "$shared/elf/ld.so"` 返回 2，
唯一编译诊断为 `XOS dynamic interpreter startup is not implemented`。
本轮未产出 `ld.so` 或 `libc.so` 的最终链接件，未运行动态客体验收。
后续由 [D0 契约](../contracts/dynamic_linking_d0.md) 约束解释器启动及资源交接。
