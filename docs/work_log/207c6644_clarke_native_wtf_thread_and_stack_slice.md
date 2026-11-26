# 207c6644 · ClarkE 原生 WTF 栈边界

2026-11-26 · 基线 `4f232e50`。直接构建锁定 WPE WebKit 2.54.2 的上游 Ninja 目标。
`Threading.cpp.obj` 和 `AutomaticThread.cpp.obj` 已通过。`StackBounds.cpp.obj` 在
`StackBounds.cpp:209` 缺少 XOS 实现。`posix/ThreadingPOSIX.cpp.obj` 在
`ThreadingPOSIX.cpp:129` 找不到 `sem_t` 及 `sem_init` 等声明。

XOS 专用补丁将 `WTF::StackBounds::newThreadStackBounds()` 和
`currentThreadStackBoundsInternal()` 接入已有 `clarke::query_stack_bounds`。WTF
`origin` 取高界，`end` 取最低可访问地址。查询失败触发发布构建断言。实际生成的失败
分支调用目标 libc 的 `abort`。上游 `PlatformHave.h:437` 默认启用
`HAVE(STACK_BOUNDS_FOR_NEW_THREAD)`。`Threading.cpp:272–286` 在持有工作线程入口锁时
启动并查询对端，工作线程先取得该锁才能进入用户函数。源锁绑定补丁和两个辅助源码的字节。

## 实际复验

Linux arm64 使用 CMake 4.4.5、Ninja 1.13.2、Ruby 3.3.8、Python 3.14.10、目标
GCC/G++ 16.2.0 与 GNU binutils 2.47。六个交叉工具核对 SDK manifest。已验 glibc
C/C++ SDK 和 ICU 79.1 目标库与 [布局阶段](89051575_clarke_native_llint_layout_bridge.md)
相同。构建在断网容器中单任务运行，限制为 1 GiB 和一个 CPU，两次正式复跑均无 OOM 终止。

```sh
python3 src/ports/webkit/build_llint_layout.py --wtf-stack \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output "$WTF_OUT"
```

三个 x86-64 `ET_REL` 对象通过格式核对。省略 `--wtf-stack` 并使用另一个新目录复跑，
原有两个 LLInt 提取器和三个生成头的五个摘要均与 `4f232e50` 的布局回执相同。

下面的客体探针调用两个已经编译的 WTF 栈查询入口，直接使用构建树的上游 `StackBounds`
类型。真实 `ld -r` 解析这两个入口与辅助对象之间的引用。剩余 `pthread_self`、
`pthread_getattr_np`、`pthread_attr_getstack`、`pthread_attr_destroy` 和 `abort` 由同一
SDK 解析。主线程和 pthread 工作线程各自核对可访问范围和活动栈地址，主线程还在
持有入口握手锁时核对新线程的栈范围。

```sh
out=$(realpath "$WTF_OUT")
obj="$out/layout/Source/WTF/wtf/CMakeFiles/WTF.dir"
x86_64-elf-ld -r -o "$out/stack_pair.obj" \
  "$obj/StackBounds.cpp.obj" "$obj/xos/xos_stack_bounds.cpp.obj"
export XOS_ICU_SDK="$GLIBC_BUILD/sysroot" XOS_ICU_CXX_INCLUDES="$out/drivers/cxx-includes.txt"
export XOS_ICU_CXX=$(command -v x86_64-elf-g++) COMPILER_PATH="$out/drivers/binutils"
"$out/drivers/cxx" -std=c++23 -O2 -DNDEBUG -DBUILDING_JSCONLY__ -DBUILDING_WEBKIT=1 \
  -DBUILDING_WITH_CMAKE=1 -DBUILDING_WTF -DHAVE_CONFIG_H=1 \
  -I"$out/source/wpewebkit-2.54.2/Source/WTF" -I"$out/layout" -I"$out/layout/WTF/DerivedSources" \
  -I"$out/layout/bmalloc/Headers" -I"$out/layout/bmalloc/PrivateHeaders" \
  -isystem "$out/icu/include" tests/fixtures/webkit/wtf_stack_smoke.cpp \
  "$out/stack_pair.obj" -o "$out/wtf_stack_smoke.elf"
python3 tests/qt6_sdk_probe.py --image "$XOS_PROBE_ISO" \
  --payload "$out/wtf_stack_smoke.elf" --marker CLARKE_WTF_STACK_OK --report "$out/guest.json"
```

QEMU 11.1.3、单 CPU、512 MiB、无网卡，临时 FAT 盘在有界 tmpfs。系统为
`8d7525f679d42e69`，镜像 SHA-256 `0c5393c3224acadeffee5cebe239fcc066fac9bb5863debfeaf6b9d9a4dbae26`。
静态 ELF 具有三个 LOAD 和一个 TLS 段。链接器仍报告 glibc 的 `raise`、`__getcwd`
警告。`xsh` 输出 `CLARKE_WTF_STACK_OK`，退出 0，资源前后均为 `129714 / 3 / 1`。
客体运行的是两个入口的正常查询路径。整理补丁上下文后，干净复跑的四个已应用源码、
三个目标对象及 `ld -r` 工件均与客体使用的构建逐字节一致。

| `build/clarke-wtf-final/` 工件 | SHA-256 |
| --- | --- |
| `wtf/manifest.json` | `6033ee735d5b2c8a1c797a69e2df1ed58d364248b5fd37e466fdbb95a0e48474` |
| `StackBounds.cpp.obj` | `3d0c2a73ce969d3598e6bff091aad2f018771b7ac243e4af25d992acd71fc405` |
| `Threading.cpp.obj` | `325a4a0bc78541e32b8c8220f03dafabef9ffeea0808709a7c69c9c4de0c8ea7` |
| `xos/xos_stack_bounds.cpp.obj` | `891f3c6d88451108be87904c1b1c9478fe1f6c0c0f7b4eb37327f2b855d00c76` |
| `wtf/stack_pair.obj` | `7828caeaecde848157055222b9c9aa961b11a3165d51ab59317c692bdcec5a31` |
| `layout/manifest.json` | `5bfd68c9c5c2b0469ab70f8a046ed4e49eab70a233f4b2218d5d677bf66c4350` |
| `guest/wtf_stack_smoke.elf` | `f44f9f0cc2da0430aef13c908f40d8e03a51d359ee1f6686f05df817cee328b2` |
| `guest/guest.json` | `9c8d0c51627d6087e7848d97d1b2b048ea5fffd248d5b08aceab232b0ba7f53b` |
| `guest/guest.serial.log` | `75a6a0890a1838e2548f74844033256c8e2b6671edf99c7d3424aaed67714dba` |

## 下一个依赖

`posix/ThreadingPOSIX.cpp` 的信号初始化从 `Threading.cpp:487` 可达。补齐 semaphore
声明只够继续编译。当前 glibc 无法用该实现的 `pthread_sigmask` 与非零 `pthread_kill`
停车和恢复 XOS peer。完整 `WTF`/`JavaScriptCore` 静态库和 `jsc` 链接未运行。

`JSLock.cpp:126–148` 在持有 VM 锁后按线程身份登记 mutator，仍允许不同线程先后进入。
`Heap.cpp:461–482` 在关闭 `useConcurrentGC` 时仍构造 `HeapThread`，且同文件
`1397–1409` 的 collector 路径向 `runCurrentPhase` 传入空当前线程状态。
`MachineStackMarker.cpp:213–222` 在这一情况下依赖复制已登记线程的活动栈与寄存器。
单 mutator 路线需要在 VM 准入时拒绝其他线程，并保证该所有者自身收集时保存当前寄存器
与活动栈。当前 GC 根扫描维持上游行为。该路线及解释器在客体中的执行尚未验证。
