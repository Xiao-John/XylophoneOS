# a1cc675f · glibc D1 共享 rtld 入口诊断

2026-11-26 · 基线 `c2a48c2b`。此前 `afa53e87` 的固定 PIC 工件已经验证高地址执行。
本轮尝试的是已验签 GNU glibc 2.44 的共享配置和实际 rtld 入口对象。

```sh
python3 -B scripts/probe_glibc_rtld.py --archive "$GLIBC_ARCHIVE" \
  --jobs 2 --output build/rtld-final-evidence
```

从 `382fd564` 在断网 Linux arm64 容器干净复跑，使用 GCC 16.2.0、GNU binutils 2.47、
GNU Make 4.4.1 和两个构建任务。内存上限 1.5 GiB，未触发 OOM。
探针复用现有签名校验、补丁和 XOS sysdeps 准备，使用独立构建目录。真实 configure
接受 `--host=x86_64-unknown-xos --enable-shared --enable-default-pie`，生成
`build-shared = yes`、`build-pie-default = yes` 和 `enable-static-pie = yes`。
直接用 bare-ELF GCC 驱动的 `-shared` 产生 `ET_EXEC`。同一个小型无 libc 编译探针
使用 `-Wl,-shared` 产生 GNU `ET_DYN` 共享对象；`-pie` 产生 `ET_DYN` PIE。
这两次链接分别验证实际工具链选项传递和 ELF 类型。

## 实际构建结果

下表的清单和日志摘要来自这次签名源复跑的归档。清单含构建路径与命令，
复跑时先核对源码、目标工件和实际结果。

- 首次从顶层执行 `make -j2 elf/subdir_lib`，依赖编译首先在原生 `fstatat.c` 报出
  `__EI___fstatat` 指向未定义的 `__GI___fstatat`。同轮 NPTL `lowlevellock.c` 的
  `__lll_lock_wait[_private]` 与 `__lll_lock_wake[_private]` 出现同类隐藏别名错误。
- 用真实上游 `elf` 规则直接构建 `rtld.os`。编译命令含 `-fPIC -DSHARED -DMODULE_NAME=rtld`，
  产物为 x86-64 `ET_REL`，包含 `_start`、`_dl_start`、`_dl_start_user`，并引用
  尚未定义的 `_dl_sysdep_start`。
- 单独编译 `dl-sysdep.os`，真实 `sysdeps/xos/dl-sysdep.c:5` 的共享启动闸门拒绝编译。
  干净目录先用上游 `csu` 规则生成 `rtld-sizes.h`，再直接构建 `ld.so`。此路径
  到达通用 `dl-execstack.c`，在 `rtld_hidden_def` 展开时报告
  `__EI__dl_make_stack_executable` 指向未定义符号。完整解释器和 glibc PIE 未链接或运行。

| 工件 | SHA-256 |
| --- | --- |
| `build/rtld-final-evidence/manifest.json` | `f1f9d3e31ea7b0cbde3034680cd9d6e073eeb9490c18a9b6f79f9f59f7a1fb77` |
| `shared/elf/rtld.os` | `928f6af32b0f7a711d0c7ef983f935a4336caca8b6147fc48cde474460ac4d89` |
| 已验签源码记录 | `062717b6279b0e1db5fd430d82d0bab7ebf4bc9da3c822eddf9e3ff302050597` |
| `configure_shared.log` | `96cfaf43390f025ac74f90e16214b087c96c1a7fe7b094a10e85b4b15dd084b1` |
| `make_dl_sysdep.log` | `6616d816befad80cd8dc556f9c3303ab20aab8ac2060f13242930636ef31aa35` |
| `make_ld_so.log` | `2463d78a7bd8d1aafa2960c8a4755f04504cddac8fc5ad6de82f24107507dd50` |
| 首次顶层 `build/rtld-first-evidence/make-elf.log` | `ee0d0abe8fabe557dd1526b06da860f322f1f517e986bd497bda86ec6b6afa78` |

## 下一处边界

`sysdeps/x86_64/dl-machine.h` 的 `_start` 将栈指针传给 `_dl_start`。`elf/rtld.c:494`
通过 `_dl_sysdep_start(arg, &dl_main)` 交给系统端。下一步是验证一条受控的原生入口交接，
以真实启动记录及实际已映射对象提供有界参数和 auxv，再决定 XOS 启动后端的接口。
该交接沿用 [D0 的启动和文件会话要求](../contracts/dynamic_linking_d0.md#52-入口auxv-与文件会话)，
涉及的共享 ABI 变更交由单独审查。栈执行权限仍由真实原生策略裁定。
