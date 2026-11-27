# glibc D2 · 当前 Net2 基线的共享工作线程

## 组合基线

基于 `25705208` 只移入工作线程生产增量。公开 dlfcn 策略继续使用 #386 的 `0038`，工作线程的保留 DTV 和已装载 GNU unwinder 成为 `0039` 和 `0040`。当前 Net2 文件会话、系统任务等待、Qt 所需的 `fstatat` 与 `fstatat64` 标志语义均来自同一源码树。内核 ABI、新包身份和启动授权继续由原有契约管理。[D0 合同](../contracts/dynamic_linking_d0.md)

从 `a38a86752c35bb6ba917eafd493834cb9bb3a822` 在断网 Linux 构建普通 ISO `80be748333203897`、验签 glibc C SDK、真实 GNU `ld.so` 和 libc。验签 GCC 16.2.0 配方在这批 `ld.so` 和 libc 上重新生成 `libgcc_s.so.1`、`libm.so.0.1`、`libstdc++.so.6`。复用既有交叉编译器和验收过的 PIC CRT 与 Dash。SDK、运行库、ISO 与客体由同一次候选构建绑定。正式 GNU 解释器仍使编译时 startup guard 生效。

## 同一闭包的客体验收

六次独立冷启使用同一实际 rtld、共享 libc 和文件会话对象。C 和 C++ 的原生入口、GNU `std::thread`、多工作线程的 TLS、GNU `pthread_exit`、以及公开加载拒绝均退出 0。每次前后的空闲页、任务数和完成记录均为 `129696 / 3 / 1`。

| 专项 | 实际观察 |
| --- | --- |
| C、C++ | C 构造、环境、auxv、文件和 `errno` 通过。缺少闭包 unwinder 的 C 路径拒绝创建工作线程。C++ 初始 TLS 和析构通过。 |
| `std::thread` | GNU 版本化入口、线程 ID、移动和 `join`，app/DSO TLS 与 `errno` 隔离。跨 DSO 异常和两处 TLS 析构均通过。 |
| 多工作线程 | 三个并发工作线程和第四个复用，回收前后核对独立 TLS、`errno` 和四次 TLS 析构。 |
| 末线程 | 初始线程经真实 GNU `pthread_exit` 退出，工作线程 `join` 得到初始线程返回值，末线程 TLS 保留到进程 `atexit`。 |
| D2-C | 四项公开装载均返回 `ENOTSUP`，`dlerror` 读取后清空。公开路径没有合法 handle。`dlclose` 从同一 ELF 的版本化入口反汇编核对策略错误与 `-1`。 |

静态 G3 线程套件在原建目录和脱离产物目录的恢复环境各通过一次。恢复环境再解包同一对归档，冷启复验 GNU `std::thread`，实际载入的 ELF、资源计数和 TLS 析构与原构建一致。归档保留 GNU `ld.so.1` 符号链接以满足 `DT_NEEDED`，首次缺少别名的接收诊断保留在原始记录中。

本次结论覆盖私有原生 GNU 固定闭包。公开动态应用启动、动态 TLS 分配与 D3 激活和代际切换各有独立验收。

[证据索引](../reports/glibc_d2_native_workers_current_20261127/manifest.json)

## 复验

`RETAINED` 指向本次原件目录 `worker-main-2570/original`，其中 `system-sdk.tar.zst` 和 `shared-runtime.tar.zst` 包含真实系统、SDK、GNU ELF 和已绑定的运行库头。`DASH` 指向包含已绑定 `dash.elf` 和 `dash.json` 的目录，`CRT` 指向已绑定 `crtbeginS.o` 和 `crtendS.o` 所在目录。原材料与运行库摘要见绑定回执。使用候选分支和有同版目标工具、QEMU 的 Linux 镜像 `PROOF_IMAGE`。`OUT` 是新输出目录。

```sh
mkdir -p "$OUT"
docker run --rm --network none --cpus=1 --memory=1250m \
  --tmpfs /proof:rw,exec,size=500m --tmpfs /project/build:rw,exec,size=64m \
  -e PYTHONPATH=/project/scripts:/project/tests \
  -v "$PWD:/project:ro" -v "$RETAINED:/retained:ro" -v "$DASH:/inputs:ro" \
  -v "$CRT:/crt:ro" -v "$OUT:/out" "$PROOF_IMAGE" sh -eu -c '
    for artifact in system-sdk shared-runtime; do
      tar --zstd -xf "/retained/$artifact.tar.zst" -C /proof
    done
    for case in c cpp shared-std-thread runtime-load-policy shared-worker shared-worker-last; do
      python3 -B /project/tests/glibc_d1_linked_interpreter_guest.py \
        --system /proof/qualification --system-source /project --sdk-build /proof/sdk \
        --gnu-build /proof/native/gnu-link --gcc-shared-build /proof/gcc-shared --pic-crt /crt \
        --dash /inputs/dash.elf --dash-receipt /inputs/dash.json --case "$case" --output "/out/$case"
    done
  '
```

完整源码重建可使用与原件同行的 `run-replay.sh` 和 `source-delta.mbox`。脚本复现原构建及补入 `ld.so.1` 别名后的封存步骤。运行时挂载冻结原档、Dash 和回执到 `/inputs`，挂载 PIC CRT 到 `/crt`，挂载工作线程原件 `worker-unwind` 到 `/history`。这里使用的历史脚本仅提供 GNU 构建命令，运行库从本分支和当前验签源码生成。
