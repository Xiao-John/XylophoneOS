# glibc D2 固定闭包中的 GNU C++ 运行库

[D0 的 D2-A、D2-B 和 D2-C](../contracts/dynamic_linking_d0.md#8-d1d4-验收与交付边界)是本次分段验收的依据。试验继承 #311 的真实 GNU 解释器、共享 libc、C SDK 和原生系统。正式 glibc SDK、入口守卫、newlib 回退和 ELF 准入沿用 #311。

## 构建与依赖

- `build_glibc_shared_gcc.py` 核对 GCC 16.2.0 归档、发布签名、GNU keyring 和固定签名者，并在空的独立目录展开。目标为 `x86_64-unknown-xos`。目标编译器、链接器和检查工具与 C SDK 绑定。
- GCC 的原生 ELF 规则生成 `libgcc_s.so.1`，保留 GNU `GCC_*` 符号版本和实际 DWARF unwinder。它从同一共享 libc 使用 `_dl_find_object@GLIBC_2.44`。
- 同一套 glibc 2.44 的 GNU math 目标生成 `libm.so.0.1`。它使用共享 libc，且浮点运算需要 GCC 的真实共享运行库。普通 GNU `atexit.oS` 为每个调用 DSO 传递自己的 `__dso_handle`。
- Libtool 从同一个验签 GCC 归档构建 `libstdc++.so.6`，使用目标 POSIX gthreads、generic locale、GNU PIC CRT、`CXXABI_*` 和 `GLIBCXX_*`。该库依赖上述 libm、libgcc_s、libc，并从解释器调用 `__tls_get_addr`。TLS 持有者登记调用 libc 的 `__cxa_thread_atexit_impl`。
- 三个新运行库均为 x86-64 ET_DYN，启用立即绑定、RELRO 和 NX stack。依赖见证来自实际 `DT_NEEDED` 和符号版本。构建产物保留 GNU 许可材料、C++ 头文件、哈希和命令回执。原始 GNU 构建使用的文件名及编号维持研究用途。

## 原生验证边界

真实 C++ PIE 从独立链接的 DSO 捕获 `std::runtime_error` 派生异常，检查跨对象 RTTI、异常文本和栈展开期间的 RAII 清理。该 DSO 的主线程 `thread_local` 持有者在退出时析构，随后应用的 `atexit` 回调确认状态。共享 libc 的 `pthread_create` 目前返回 `ENOTSUP`，客体检查了该行为。工作线程 TLS 和析构、运行期装载和卸载、SDK 激活和发布仍是后续门禁。

试验只向既有私有 handoff 提交经过哈希核对的打开实例。每个依赖通过固定 SONAME 授权。缺少对应授权的对照将相同的 `libgcc_s.so.1` 放在同一 FAT 文件系统上，检查 GNU rtld 启动拒绝和资源恢复。旧 C、C++、缺 libc 授权三项以同一原生 ISO 复验。

共享 C++ 客体诊断使用 512 KiB 私有启动堆上限和 90 秒启动窗口。原 D1 诊断仍使用 128 KiB 和 30 秒。一次 30 秒的完整闭包试跑在 libm 映射阶段结束，资源回到基线。验证按现有文件消息的数据容量分块，保留同一会话和同一打开实例。该诊断仍受实际 XOS VM 和文件会话限额约束。

[绑定回执](../reports/glibc_d2_shared_cxx_20261127/binding.json)记录系统 `8d8d22c07d5f48d2` 上的五项结果。共享 C++ 正常退出为 0，依赖授权缺失退出为 127，两次宿主计时分别为 32.401 秒与 25.261 秒。五项客体前后均为 129696 个空闲页、3 项任务、1 项完成记录。原生官方 `dl-sysdep.os` 构建仍命中启动守卫。

## #311 合入后的复验

从 `7f61a15a68f7cce37dbf68120e6de83c885d5afa` 重新构建验签 glibc 2.44 C SDK、普通系统、GNU 解释器和 libc，以及验签 GCC 16.2.0 的共享闭包。系统 ID 为 `f339237e4a35f275`。后续主线 `f09f2f7f` 的差异限于文档、证据和可选浏览器传输组件，保持本次 SDK、正常系统和启动验收的相关实现一致。

第一次完整 C++ 闭包运行在正常 bootstrap 进程启动后等待退出超时，保留串口和失败回执。相同 SDK、ISO、bootstrap 和动态 ELF 的独立重跑完成跨 DSO 异常、TLS 析构及进程退出，客体命令用时 32.474 秒。缺少 `libgcc_s.so.1` 授权退出 127，用时 25.310 秒。C、C++ 和缺 libc 授权三个原用例也通过。五个用例前后的资源均为 129696 个空闲页、3 项任务、1 项完成记录。官方解释器编译再次命中启动守卫。

[当前回执](../reports/glibc_d2_shared_cxx_20261127/current_main_replay.json)记录已验签输入、五组通过、一次超时和快照哈希，保留上面的原始验收。

## 重跑

使用 #311 [发布回执](../reports/glibc_d1_linked_interpreter_20261127/publication_replay.json)对应的 C SDK、GNU 解释器构建树、PIC CRT、dash、系统镜像和系统源。若重用原系统镜像，`--system-source` 要指向它的原始源码。验收 runner 检查系统全文件哈希清单及系统 SDK。

在带目标 GCC 和 QEMU 的 Linux 构建环境中，复制 #311 的已配置 GNU 构建树作工作副本。其配置记录的 glibc 源和构建路径须与当前环境匹配。保持原 GNU 链接产物用于后续客体绑定。命令中的变量全部指向明确的输入或新输出目录。

```sh
python3 -B scripts/build_glibc_shared_gcc.py \
  --archive "$GCC_ARCHIVE" --signature "$GCC_SIGNATURE" --keyring "$GNU_KEYRING" \
  --sdk-build "$C_SDK" --glibc-source "$GLIBC_SOURCE" --gnu-build "$GNU_BUILD_COPY" \
  --pic-crt "$GCC_PIC_CRT" --output "$CXX_BUILD" --jobs 1

for fixture in shared-cxx shared-cxx-unlisted c cpp unlisted; do
  python3 -B tests/glibc_d1_linked_interpreter_guest.py \
    --system "$XOS_SYSTEM" --system-source "$SYSTEM_SOURCE" --sdk-build "$C_SDK" \
    --gnu-build "$GNU_BUILD" --pic-crt "$GCC_PIC_CRT" --gcc-shared-build "$CXX_BUILD" \
    --dash "$DASH_ELF" --dash-receipt "$DASH_RECEIPT" --case "$fixture" --output "$REPLAY/$fixture"
done
```

原始构建、输入及客体回执的三个本地快照及其 SHA-256 记录在绑定回执中。公开 JSON 用变量表示宿主工作目录，原始串口日志压缩保存。
