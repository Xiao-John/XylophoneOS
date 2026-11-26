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
