# 34ad6712 · 私有 GNU 共享运行库可重建入口

本模块补齐仓库实际缺失的 GNU rtld/libc/PIC CRT 构建入口。此前已有 D1/D2
真实运行代码和客体，但构建重放依赖历史临时目录。现在从认证的 glibc 2.44、
GCC 16.2.0 源及匹配的静态 C SDK，在新目录中完整构建，并以真实 C 客体验证。
范围仍是**私有、固定启动闭包**，不是 D3/D4 全部或默认动态 SDK。

## 构建

新增 `scripts/build_glibc_shared_runtime.py`。它精确绑定输入 SDK、编译器、
源认证、移植文件、recipe 与 native 支持材料，从同一已验归档快照解包。
native support 的 PIC 版本从 SDK 已携带的源码重建，不执行回执中的命令字符串，
不混入 newlib 头或对象。GNU PIC CRT 从同一已认证 GCC 源生成，不能以裸机
`crtbegin.o` 代替 `crtbeginS.o`。

```sh
xos-sdk --workdir "$WORKSPACE" python3 "$SOURCE/scripts/build_glibc_shared_runtime.py" \
  --sdk-build "$GLIBC_SDK" --glibc-archive "$INPUTS/glibc-2.44.tar.xz" \
  --gcc-archive "$INPUTS/gcc-16.2.0.tar.xz" \
  --gcc-signature "$INPUTS/gcc-16.2.0.tar.xz.sig" \
  --gcc-keyring "$INPUTS/gnu-keyring.gpg" --output "$RUNTIME_BUILD" --jobs 2
```

实际输出包括 `gnu/elf/ld.so`、`gnu/libc.so`、GNU `Scrt1.o/crti.o/crtn.o`、
同一早期文件会话对象、PIC native support 及 `pic_crt/target/libgcc` 中的
`crtbeginS.o/crtendS.o`。`gnu/elf/ld.so.1` 必须是同一真实解释器的 GNU 别名。
manifest 保留 `private_runtime_built_not_run`，客体资格在独立回执中，不倒改
构建产物的状态。

官方 `dl-sysdep.os` 的 SHARED 编译首先实际执行，并必须仍拒绝未实现的公开
启动。私有 composition 显式选择已经存在的 `xos_rtld_sysdep_invoke`，继续
使用上游 glibc 算法。没有删除守卫、写假 resolver 或给 rwx/RELRO 失败放行。

GNU `make lib` 同时构建 hosted audit 工具 `sotruss-lib.so`。第一次重建的
真实失败是该工具错误带入非 PIC bare-metal CRT；原始错误和 recipe report
保留。最终 recipe 用一个具名 `xos-private-fixed-closure=yes` 构建选择，
仅排除此 profile 已明确禁止且不交付的 audit 工具。实际目标构建返回 0，
没有把失败的 `make lib` 当作成功。该精确 Makefile 变换及结果摘要均有回执。

## 实际验证

运行环境为已验 SHA-256 的 SDK Preview 2 Linux x86-64，归档摘要
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
SDK launcher 普通模式运行；宿主不支持其 offline 网络隔离模式，不声称隔离。
匹配系统由 `732e29f` 源构建，build_id `d2f006e5b36d293a`；该源码快照与系统
manifest 在每轮前后重新核对。Dash 从独立 glibc C profile 重建。

| 检查 | 结果与范围 |
|---|---|
| glibc/GCC 实际签名、精确源码/工具/SDK 绑定 | 通过；GCC 更新身份见 [源码认证记录](9b82d2f0_gcc_shared_source_auth.md) |
| 官方共享 startup 守卫 | 实际拒绝，诊断匹配 |
| 最终 tracked recipe 从新目录重建 | 通过；真实 GNU rtld/libc 和 PIC CRT，不复用旧共享对象 |
| 原生 C + 版本化 libc + constructor/env/auxv/file/errno | 新产物 `passed_subset`；正常退出 0，页/进程/句柄基线恢复 |
| 未列入闭包的 libc | 新产物 `passed_subset`；未进 main，实际 rtld 缺库诊断，退出 127，基线恢复 |
| 共享 C++ / std::thread / app 与 DSO TLS 析构 | 前序独立初始 composition 实际通过；其准确输入另存，不重贴为最终 recipe 产物 |

最终 C 两轮基线均为 `[129709, 3, 1]`，前后相等。共享 GCC 单独真实构建出
`libgcc_s.so.1`、`libm.so.0.1`、`libstdc++.so.6`，DT_NEEDED 图符合现有约定；
共享 C++ 运行使用它自己绑定的初始 glibc/rtld/PIC CRT，而不是新的 C recipe
输出。这一边界保留，不能从相近配置推定两套产物的资格相同。

## 证据与下一步

[平铺证据索引](../reports/glibc_runtime_rebuild_20261127/manifest.json)包括最终
build record、官方守卫日志、C 正反客体及原始共享 C++ 回归、首次失败报告与
截取的尾部日志。公开文件是路径占位符导出，binding 保留每份原始摘要、长度与
转换说明。完整原始 build logs 保留在构建目录；重复的已完成源解包和失败
中间对象可以从认证归档恢复，清理不会删除唯一源码或原始失败记录。

公开 native identity、真实 ELF 与 generation 图交叉验证、同一 pins 的父子
交接、authenticated ready/deadline、exec 提交边界与最终 SDK/发行资格继续为
P0。当前 `dlopen/dlmopen/dlclose` 的固定闭包拒绝政策没有改变。下一模块使用
实际重新构建材料完成这些公开路径，不把本次 C 运行替代它们。
