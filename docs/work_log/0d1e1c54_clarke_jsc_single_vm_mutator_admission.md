# 0d1e1c54 · ClarkE JSC 单 VM mutator 准入

2026-11-26 · 从 `2d8ee687` 继续。锁定 WPE WebKit 2.54.2 中，`VM.cpp:320` 在构造 VM
时取得 `JSLockHolder`。`JSLock.cpp:144` 的 `didAcquireLock` 是 `MachineThreads::addCurrentThread`
的唯一调用者。`DropAllLocks` 的恢复也调用同一个 `JSLock::lock`。

XOS 在取得内部锁后保留首个线程的 `RefPtr<Thread>`。任何新持有者都必须与该 WTF 对象
相同。检查在发布临时锁所有者和调用 `didAcquireLock` 之前，避免第二个线程访问堆或加入
根扫描组。强引用让对象地址在释放锁、线程退出后仍保留。对同一线程的递归取得和临时
释放后的恢复分别增加锁深度、重新核对身份。

## 目标编译

直接请求 Ninja `JavaScriptCore.dir/runtime/JSLock.cpp.obj` 也启动 `bmalloc`、WTF 等
库的编译。该次构建在观察到库的依赖后中止。`--jsc-mutator` 关闭合并和预编译头，执行
上游 `JavaScriptCore_CopyPrivateHeaders`、`JavaScriptCore_CopyHeaders`、`WTF_CopyHeaders`
及 `bmalloc_CopyHeaders`，再执行 CMake 生成的实际 `JSLock.cpp` 目标编译命令。

```sh
python3 src/ports/webkit/build_llint_layout.py --jsc-mutator \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output build/clarke_mutator
```

干净复跑在断网 Linux arm64 容器中通过，单 CPU、单构建任务，内存上限 1 GiB，
没有 OOM 终止。
使用 CMake 4.4.5、Ninja 1.13.2、Python 3.14.10、目标 GCC/G++ 16.2.0 和 GNU
binutils 2.47。目标工具的字节摘要与已验 glibc C/C++ SDK 一致，ICU 79.1 来自同一
锁定输入。`readelf` 核实 x86-64 `ET_REL`。发行对象中 `JSLock::lock(long)` 的线程
指针对比位于临时锁发布及 `didAcquireLock` 之前，失配分支调用 `abort`。

`--wtf-stack` 复跑的三个目标对象、默认布局阶段的五个 LLInt 工件均与 `2d8ee687`
逐字节一致。另行编译 `posix/ThreadingPOSIX.cpp.obj` 仍在 `ThreadingPOSIX.cpp:129` 报告 `sem_t` 缺失，
并在第 110 行报告 `sem_init` 缺失。

| `build/clarke-mutator-evidence/` 工件 | SHA-256 |
| --- | --- |
| `manifest.json` | `4e34bf224418618df2e011817435d2dd2d4a00aaed6d86336746d604357f44d4` |
| `JSLock.cpp.obj` | `ebc3bc3e5647dded3daccf29efcbef9f9559049a714c070b58187442f418cf7d` |
| `jslock-machine-code.log` | `095ad73df2a7d59d07bbe14a29487a3a5af589a7bb646f1744429c9e1c286410` |
| `wtf-regression/manifest.json` | `10cac305e825e722bf0ae1f6f2bcc5f23fcf6ca3061a1b12cd151c629f29a613` |
| `wtf-regression/posix-known-blocker.log` | `e5790f45de3996a8f4d206dbe840cef99ed620ad63389990913f05d145241bd3` |
| `layout-regression/manifest.json` | `1bda4e643c16e6c6451e1fe0a4c18d26c31a01e4bac1bf86f316f12181d76bd8` |

## 执行前置条件

- `Threading.cpp:487` 会在 WTF 初始化时调用 `initializePlatformThreading`。
  现有 `posix/ThreadingPOSIX.cpp` 仍需头文件中的 `sem_t` 等声明，信号挂起还依赖
  `sigaction`、`pthread_sigmask`、非零 `pthread_kill`、`sigsuspend` 及机器上下文。
  XOS 线程后端需要实现在用的 pthread 路径，并在 GC 开始前确立可用的根采集路径。
- `Heap.cpp:1397` 的 collector 入口向 `runCurrentPhase` 传入空当前线程状态，
  `Heap.cpp:2200` 的释放堆访问路径可将收集交回后台线程。关闭 `useConcurrentGC`
  仍保留此路径。真正的单 mutator 解释器必须把根采集安排在 VM 所有者上，确保
  `MachineStackMarker.cpp:213` 收到当前寄存器和栈。上游挂起失败后的跳过行为不能
  视为有效的活线程根采集。
- `VM.cpp:254` 默认使用构造线程的 `RunLoop`，也允许显式指定另一 run loop。
  `JSRunLoopTimer.cpp:125` 按 VM 的 run loop 注册定时器。完整单线程运行前须验证
  定时回调、VM 销毁及终止都在所有者线程完成，并实际验证 GC 根保留。

完整 WTF 和 JavaScriptCore 静态链接及客体准入、解释器执行未运行。
