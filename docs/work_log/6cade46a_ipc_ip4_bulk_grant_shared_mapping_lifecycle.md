# 6cade46a IPC IP4 Bulk Grant Shared Mapping Lifecycle

## 范围与交付

实现 sys88 IP4 grant create/delegate/map/unmap/close，提供 SDK wrappers 和 owner 可运行的真实客体验收脚本。基线为 PR #111 的合入主线（IP3 acceptance 已通过：head `c36da914`，build id `effc4a6ff4aacf4e`，guest runs=3，资源 `[129826,3,1]` 前后守恒）。未修改 IP3 的 feature 支持状态。没有修改 `docs/state.md`，IPC feature query 与 SDK manifests 继续保持 unsupported。

- 共享 ABI：追加 action 19–23、grant request structs、rights/access、busy 错误和固定额度。
- 内核：单独分配的 backing user pages、同步 source snapshot/zero-fill、每映射引用、权限受限映射、map id、VM reservation 冲突检查、busy pin 检查和 close/exit/fault/exec 回收。
- SDK：grant create/delegate/map/unmap/close 封装。
- guest probe：真实跨进程写共享、进程退出映射撤销、只读权利、同进程别名、64 映射容量、map/close 并发、pin-blocked close 和资源基线。

## 设计与边界

grant backing 不借用进程现有页，不依赖未交付的 COW，也不暴露物理地址。创建时至多 64 页，最多 16 grant、64 活动映射。映射页计入接收方进程页配额；只提供 read/read_write，NX。delegate 只能缩减 `read_mapping/write_mapping/manage/delegate` 权利。map 使用现有高位匿名 VM arena 的精确 reservation；重叠的 VM 操作在开始前返回 IPC `busy`。撤销先扫描所有映射的阻塞 pin，发现 pin 时无副作用返回 `busy`；成功后撤销全部映射/handle 并释放映射与 backing refs。单 CPU syscall gate 序列化 map/revoke。DMA/MMIO 与 SMP shootdown 不在此范围。

## 检查与证据

- IP3 合并基线依据：GitHub PR #111 acceptance 记录；IP3 probe 的 `tests/ipc_v1_guest.py` runs=3 通过，资源守恒。
- guest 资格脚本：`python3 tests/ipc_v1_grant_guest.py --system <same-build-system-dir> --sdk <same-build-threading-sdk> --output <new-output-dir>`；**本轮未运行**，由维护者运行验收。
- 完整目标构建：`make build` 未运行到编译，因环境缺少 NASM；`x86_64-elf-g++` 交叉编译器也不可用。
- 严格 host C++ syntax：内核 `tasks.cpp`（使用临时生成头文件占位）与 IP4 guest fixture 均通过 `-Wall -Wextra -Werror -Wconversion -Wshadow -fsyntax-only`。
- 文档一致性、ABI 文档一致性、Python `py_compile` 与 `git diff --check` 通过；公开路径扫描待 staging 后运行。
- IP4 guest qualification 未运行；不运行 IP3 guest qualification（已由 PR #111 acceptance 通过）。
- manifest/query：静态核对保持 registered_unsupported / supported mask 0。

## 未完成与下一步

真实 guest acceptance 未运行，不能据此启用 bulk_grant 或修改任一 SDK manifest。维护者运行脚本，检查 cross-process grant, manager close race, quota exhaustion/recovery, process exit reclamation 和资源回归；额外验收 exec 替换清理。单核实现不表示 SMP 支持。
