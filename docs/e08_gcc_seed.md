# E08-4：XOS 内的 GCC C Seed

当前为静态 C 工具链子集。GCC driver、cc1、GNU as/ld/ar/ranlib 在 XOS 内执行，
宿主只离线安装、核对产物，不代编。正式版本/哈希/验收结论见 state.md 与
work_log/0020_seed_integration.md。E08-5 G++/目标标准库及E08-6集成仍未完成。

## 构建与安装输入

从端原始交付保留 src/ports/gcc/seed_manifest.json；不要把其原始gcc直接拿来验收，
它仍含lrealpath漏返回值与旧libc。当前派生工具位于
.cache/xos_seed/gcc/relinks/open_capacity_fix/，manifest记录完整链接输入/输出哈希。
SDK v4为 .cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490，
manifest SHA256与目录名相同；v2/v3保留为历史。最终系统全局build_id可晚于SDK
metadata，测试逐项核对实际CRT/库/user.ld；metadata相同不是唯一依据。

组合安装清单：

```sh
python3 scripts/prepare_gcc_seed.py \
  --gcc-manifest .cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json \
  --binutils-manifest .cache/xos_seed/binutils/build/a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479/manifest.json \
  --output-root build/gcc_bundle
```

这一步只生成清单，不写工作盘；171项原组合加as alias后，当前Seed172项、sysroot151项。
如未来输入变化，以预检报告实际数量/哈希为准。离线导入必须使用白名单中的显式
source root与guest_path，QEMU挂载期间不得调用离线导入/导出。

正式功能gate会预检、创建专用2GiB FAT32临时盘、安装、启动并执行、关闭QEMU后
导出比对，不改日常盘：

```sh
python3 tests/gcc_seed_smoke.py \
  --seed-manifest build/gcc_bundle/seed_manifest.json --seed-root . \
  --sysroot-manifest build/gcc_bundle/sysroot_manifest.json --sysroot-root .
```

只需检查安装合同可加 --preflight-only，状态preflight_only、guest_execution=not_run，
不能当客体gate通过。结果在 build/gcc_seed_smoke_report.json，串口同名前缀serial.log。
后续压力由专人负责，不因这份说明重复历史轮次。

## 客体使用

清单导入后的sup>示例（预先存在/src、/out及源码）：

```text
exec-driver /usr/bin/x86_64-elf-gcc --sysroot=/sysroot -I/src -c /src/main.c -o /out/main.o
exec-driver /usr/bin/x86_64-elf-gcc -v -static --sysroot=/sysroot /out/main.o -o /out/app.elf
exec-file /out/app.elf
```

编译驱动需要显式exec-driver的直接子构造权，普通exec-file不授予。as安装了真实
同字节/usr/bin/as别名，GCC内部可经posix_spawnp查找；链接specs显式走真正
/usr/bin/x86_64-elf-ld，无collect2二次构造权。当前collect2虽在原安装清单内，
未重链接/未验收，不应把它用于正式profile。禁用LTO、共享/动态链接、线程、插件；
普通C文件open接受O_NOCTTY，files每会话16打开、全局32锁，耗尽仍报真实错误。

/sysroot/include与/sysroot/lib来自明确SDK；目标libgcc位于GCC安装目录。
XOS CRT负责构造/frame注册，profile不重复链接crtbegin/crtend。当前specs是固定
/sysroot的XOS静态profile，不能据--sysroot选项宣称任意可重定位sysroot均已支持。
-v里的Configured with是构建来源，实际include/child路径必须在客体；诊断区分两者。

当前只验收小型真实C项目、libgcc 128位辅助函数、错误码、源码保护和逐命令资源
回收。未验压力峰值、完整POSIX、G++或自举。host工具自身的libstdc++采用
-fno-exceptions/-fno-rtti，不能代替目标E08-5库。
