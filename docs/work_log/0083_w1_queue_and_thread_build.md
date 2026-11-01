# 0083：W1 输入队列与线程构建隔离

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-29。新增有界字节队列 `src/kernel/include/xos/byte_queue.hpp`：满队列保留已接收
字节、丢弃新字节并饱和计数；调用方须串行化所有操作与生产中断。当前没有接到串口、
中断、等待或用户接口，不能据此宣称终端输入已经实现。

`tests/fixtures/ncursesw/byte_queue_test.cpp` 的宿主程序在空队列、满队列、溢出、回绕和
FIFO 顺序检查通过；同一源码以 x86_64-elf 交叉编译通过。未运行 guest，也未检验 IRQ
并发、队列溢出的用户可观察语义或资源回收。需要将队列接入受控设备和原子等待后进行
专项测试。

线程 SDK 构建器增加 `--cpp-work-dir`，允许在新的私有目录构建 C++ 和 unwind，避免
改动共享的旧缓存；默认行为保持。需要保留实际构建结果、探针及线程运行验证的独立
证据，不从其他 SDK 借用静态库冒充匹配。

以匹配的多字节 threaded newlib 和 GCC 16.2.0 源码执行：

```text
python3 scripts/build_threading_sdk.py --newlib-prefix ${XOS_SCRATCH}/xos_w1_newlib_20261029/threaded/prefix --gcc-source .cache/xos_seed/gcc/source/gcc-16.2.0 --output build/w1_utf8_threaded_cpp_20261029 --logs-dir build/w1_utf8_threaded_cpp_logs_20261029 --cpp-work-dir ${XOS_SCRATCH}/xos_w1_threaded_cpp_work_20261029 --cpp
python3 build/w1_utf8_threaded_cpp_20261029/compile.py --c tests/fixtures/ncursesw/wide_locale_probe.c -o ${XOS_SCRATCH}/xos_w1_utf8_threaded_cpp_probe.elf
```

两步成功，线程候选 manifest SHA256 为
`628685c1361ac3102424c89ec47ce2343387fc3a30534c44087b47f4a6742562`，链接后的探针 SHA256
为 `4fddd411ed9ceb2973f4e692f061de9571c8192815a601b9bcb4dc1a667d260f`。这消除了 0082 的
非 C++ 候选缺失链接依赖，仍仅为交叉构建证据；UTF-8 locale、线程安全和客体行为未运行。
