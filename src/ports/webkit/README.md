# ClarkE WebKit 目标配置

本阶段配置 JSCOnly 的静态解释器路线。XOS 同时在 WebKit 的 CMake 目标和 WTF
平台判断中拥有独立标识。补丁未把 XOS 归入 Linux 或通用 Unix。实际可用的内存、
线程及文件接口在后续端口实现时逐一接入。

## 复现

从 [锁定归档](source_lock.json) 核对下载件以及补丁的 SHA-256。解包到新输出目录。
使用已通过来源认证的 glibc C/C++ SDK sysroot，保留宿主与目标库隔离。

```sh
patch -d "$WEBKIT_SOURCE" -p1 -i "$PWD/src/ports/webkit/patches/0001_xos_platform_identity.patch"
cmake -S "$WEBKIT_SOURCE" -B build/webkit-m0/target-xos-jsc -G Ninja \
  -DPORT=JSCOnly -DENABLE_JIT=OFF -DENABLE_STATIC_JSC=ON \
  -DCMAKE_SYSTEM_NAME=XOS -DCMAKE_SYSTEM_PROCESSOR=x86_64 \
  -DCMAKE_C_COMPILER=x86_64-elf-gcc -DCMAKE_CXX_COMPILER=x86_64-elf-g++ \
  -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY -DCMAKE_SYSROOT="$GLIBC_SYSROOT" \
  -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
  -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY -DCMAKE_C_FLAGS=-D__XOS__ \
  -DCMAKE_CXX_FLAGS=-D__XOS__
```

2026-11-26，CMake 4.4.4、GNU GCC/G++ 16.2.0 在锁定 WPE WebKit 2.54.2 上完成
编译器 ABI 检查，越过原先的平台识别失败。配置随后因目标缺少 ICU（至少 70.1）
的头文件和 `data/i18n/uc` 静态库结束。实际日志在
`build/webkit-m0/target-xos-jsc.log`。静态编译器探针只确认工具配置与对象生成，
完整平台工具链链接、解释器产物及客体仍待验证。

## 原生 LLInt 布局生成

`build_llint_layout.py` 在 Linux 上用锁定的 WPE 归档、已验 glibc C/C++ SDK 和
与该 SDK 配对的 ICU 79.1 目标归档生成 x86-64 LLInt 汇编头。输入 ICU 包的摘要和
其中三个静态库的摘要在源锁的 `llint_icu`。该包来自已验签 ICU 源的目标构建。

宿主使用 CMake、Ninja、Ruby、Python、Perl 和 C 编译器。构建器从锁定源码生成宿主
`unifdef`，并核对目标编译器和 binutils 与 SDK 回执相同。选择 JSCOnly、静态链接、
系统分配器和原生 x86-64 LLInt，禁用 JIT、WebAssembly 与采样分析。只构建
`LLIntAssembly.h` 的依赖，目标编译仅一个任务。

```sh
python3 src/ports/webkit/build_llint_layout.py \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" \
  --output build/clarke_llint_layout
```

`manifest.json` 绑定实际生成的设置、偏移请求和汇编头，以及两个静态目标提取器。
宿主 Ruby 从提取器读取目标编译时写入的设置表与偏移表。解释器链接、执行和跨线程
GC 仍各自验收。 [验证记录](../../../docs/work_log/89051575_clarke_native_llint_layout_bridge.md)

## 原生 WTF 栈边界对象

在同一个构建入口添加 `--wtf-stack`，并指定一个新输出目录。该阶段编译上游 WTF
的 `StackBounds.cpp`、使用该接口的 `Threading.cpp` 和 XOS 的 `xos_stack_bounds.cpp`。
回执记录三个 x86-64 ELF 可重定位对象。WTF 从 glibc 查询当前线程和尚在启动握手中
的新线程的真实栈范围，查询失败时触发发布构建断言。解释器链接和运行仍依赖线程挂起
与 GC 生命周期的实现。 [验证记录](../../../docs/work_log/207c6644_clarke_native_wtf_thread_and_stack_slice.md)

## JSC 的 VM 线程准入

为构建入口指定 `--jsc-mutator` 和新输出目录，生成 JavaScriptCore 的原生 `JSLock.cpp`
对象。这一步关闭上游合并编译，保留实际的 JSCOnly 目标依赖。XOS 的 VM 只接纳首次
取得该 VM 锁的线程，第二个线程在访问 VM 堆前触发发布构建断言。完整解释器仍依赖
线程后端和 GC 调度。 [验证记录](../../../docs/work_log/0d1e1c54_clarke_jsc_single_vm_mutator_admission.md)

## XOS WTF pthread 与基础运行库

为现有入口指定 `--wtf-pthread` 和新的输出目录。这个阶段编译目标的栈查询、
线程生命周期与 POSIX 线程实现。XOS 的正常线程初始化使用实际 pthread 与 TLS。
当前平台对跨线程暂停返回 `ENOTSUP`；恢复和读取暂停线程寄存器要求真实暂停支持。

在同一配置上构建 Ninja 的 `WTF` 目标可生成完整的目标归档。
XOS 的进程号、页大小和熵沿用已绑定的 glibc 接口。内存占用返回当前进程
计费的逻辑用户页。WTF 的保护接口调用目标 `mprotect` 并检查实际结果。
[构建与客体回执](../../../docs/work_log/73cec3d9_clarke_wtf_native_runtime.md)记录
实际线程、页保护、文件映射错误和资源回收。JSC 静态配置页、分配器和 VM GC
另行验收。
