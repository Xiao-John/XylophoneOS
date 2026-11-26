# ClarkE 原生 WTF 运行库

从 `4089796a` 构建锁定 WPE WebKit 2.54.2 的 JSCOnly、无 JIT 静态目标。
WTF 源码至 `73cec3d9d7b45296720c18aacf30ab7f789b054d`，原生客体夹具在
`65284409`。XOS 的普通 pthread 初始化保留真实生命周期与 TLS。不可用的
Unix 信号初始化不进入正常启动路径。跨线程暂停返回 `ENOTSUP`，恢复与读取
暂停寄存器强制要求实际支持。进程号、退出、页面大小、每次至多 256 字节的
熵输入均使用本版 glibc 的真实实现。最初符号检查可见 `sysconf`，链接时确认
它是桩，最终调用 `getpagesize`。

WTF 的 `memoryFootprint` 使用 sys50 返回的当前进程计费逻辑用户页与原生页大小。
构建器单独记录复用的 XOS ABI 头文件。文件映射通过实际 libc `mmap` 反馈
`ENOTSUP`。配置保护使用实际 `mprotect` 并检查结果。现有 XOS 保护仅接受
匿名保留范围，静态映像内配置的数据页需要完成真实布局与保护。

## 构建和运行

Linux arm64、CMake 4.4.5、Ninja 1.13.2、Ruby 3.3.8、Python 3.14.10，
目标 GCC/G++ 16.2.0 和 GNU binutils 2.47。核对已验签 glibc/GCC 源生成
的 C/C++ SDK、匹配的 ICU 79.1 目标档和 WPE 源锁。容器断网后编译。
两棵临时树同时存在时，曾发生一次 `cc1plus` OOM 终止。保留一棵树后的
单作业重建完成；cgroup OOM 计数未再增长。全新树的 339 步 WTF 目标通过，
随后在同一树用最终两处配置及页大小补丁增量重建归档和静态夹具。

```sh
python3 src/ports/webkit/build_llint_layout.py --wtf-pthread \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output "$WTF_OUT"

export XOS_ICU_SDK="$GLIBC_BUILD/sysroot" XOS_ICU_CXX_INCLUDES="$WTF_OUT/drivers/cxx-includes.txt"
export XOS_ICU_CC="$(command -v x86_64-elf-gcc)" XOS_ICU_CXX="$(command -v x86_64-elf-g++)"
export COMPILER_PATH="$WTF_OUT/drivers/binutils"
cmake --build "$WTF_OUT/layout" --target WTF --parallel 1

layout="$WTF_OUT/layout"
source="$WTF_OUT/source/wpewebkit-2.54.2"
"$WTF_OUT/drivers/cxx" -std=c++23 -O2 -DNDEBUG -DBUILDING_JSCONLY__ -DBUILDING_WEBKIT=1 \
  -DBUILDING_WITH_CMAKE=1 -DBUILDING_WTF -DHAVE_CONFIG_H=1 \
  -I"$source/Source/WTF" -I"$layout" -I"$layout/WTF/DerivedSources" \
  -I"$layout/bmalloc/Headers" -I"$layout/bmalloc/PrivateHeaders" \
  -isystem "$WTF_OUT/icu/include" tests/fixtures/webkit/wtf_pthread_smoke.cpp \
  -Wl,--start-group "$layout/lib/libWTF.a" "$layout/lib/libbmalloc.a" \
  "$WTF_OUT/icu/lib/libicui18n.a" "$WTF_OUT/icu/lib/libicuuc.a" "$WTF_OUT/icu/lib/libicudata.a" \
  -Wl,--end-group -o "$WTF_OUT/wtf_pthread_smoke.elf"

unset COMPILER_PATH
python3 tests/qt6_sdk_probe.py --image "$XOS_PROBE_ISO" \
  --payload "$WTF_OUT/wtf_pthread_smoke.elf" --marker CLARKE_WTF_PTHREAD_OK \
  --report "$WTF_OUT/guest.json"
```

QEMU 11.1.2 的常规系统 `27b469b7e3c35968` 从 Xsh 启动目标 ELF。WTF
初始化、主线程和工作线程身份与栈、条件唤醒和 join 全部通过。活工作线程的
暂停返回 `ENOTSUP`，随后照常回收。真实熵调用覆盖两次 513 字节请求。匿名区
保留本身不计费，提交增加三页，实际只读保护成功，释放后恢复原占用。非空文件的
映射保留 `ENOTSUP`。来宾输出 `CLARKE_WTF_PTHREAD_OK` 且退出 0，资源前后为
`[129698, 3, 1]`。ELF 为 x86-64 静态可执行体，三个 LOAD 段和一个 TLS 段。

## 到达边界

完整 WTF 归档和独立夹具已链接。JavaScriptCore 归档与 shell、VM 初始化和
脚本执行仍待验证。普通解释器启动还需要：

- `OSAllocatorPOSIX::tryReserveAndCommitImpl` 目前直接以可读或可写保护请求
  匿名 mmap。本版 SDK 实际拒绝直接的可写匿名请求。独立夹具按现有契约使用
  `PROT_NONE` 保留并经 `mprotect` 提交后通过。分配器需采用这一路径并保留
  guard、对齐、回滚与回收语义。
- `Config::finalize` 中的静态配置数据须进入受支持的真实保护布局。当前夹具只
  在自己的匿名保留区测试只读保护。
- `Heap.cpp` 将 collector 状态传给 `runCurrentPhase`，但后台路径没有当前
  mutator 的寄存器和栈。当前单 mutator 约束需要让所有者采根，并让需要 VM 锁的
  RunLoop 工作也在所有者线程运行。之后才可验收实际脚本、对象分配与回收。

| 工件 | SHA-256 |
| --- | --- |
| WPE 源归档 | `f3284e19e47fcb5ac8c63c2e1c113dbd65b2423eb8a545f5b345707829004f56` |
| ICU 目标归档 | `d64f090773eb9027bf9e0d46c95c8a60ed6d0817429f516c3807c0554178acb4` |
| glibc C/C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| glibc C/C++ profile | `3aa343495c26d715460fed84480014ab505c1a6f92976a3c6eb617341ef6562c` |
| 173 成员的薄 WTF 归档 | `2e617217eabb9460c99844bb9a12ad04b340a6d8371c1806be60b75668f9fe28` |
| XOS memory footprint 对象 | `659909fd2a6abb885845cda61b071b3c6534060f4adbec8dd395a54ee56b3c79` |
| 独立夹具 ELF | `9174f0d15e2aebd298467ef7f11422dede341f7e3230ce65e206da665575b119` |
| ISO | `ad502c5b9ba83bc1e96f33fdd56da82672c7e25feb344449b7c907d3cc8514e0` |
| 版本化夹具的来宾回执 | `eda42198a1debdfdb9ce9d1c9ec2328834913da1a373f4b72b1e674a5b85e8e3` |
| 版本化夹具的串口记录 | `2422c3fc29421aa1c96208f26985ba4f9871a4287bb99dd6c28acafd9accc9fa` |
