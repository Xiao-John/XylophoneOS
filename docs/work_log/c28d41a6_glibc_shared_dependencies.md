# G3 公共依赖汇合

2026-11-25。本分支为出站进程和后续完整 G3 组合提供一个可审阅的共同基底。
普通应用功能各自在原专项 PR 继续维护，复用同一实现；main 保持原有状态。

| 依赖 | 本分支合入的实现 |
|---|---|
| PR154 | 来源签名、不可变归档验证/解包、工具与完成路径复查 |
| PR156 | 活跃线程正常退出的有界清理窗口、owner/deadline、mode0 降级拒绝 |
| PR157 | 统一 file RPC/lease、操作17与21回复修复、输入前后绑定及真实 FatFs 回归 |
| PR161 | 原生 wait-any、nonblock、子进程认证/领取；完整status和系统身份验收复查 |
| PR158 的通用 IPC 部分 | 成功 exec 后撤销镜像拥有的端点/名称，失败 exec 保留；独立于网络服务实现 |
| CRT 初始化 | GNU ELF init_array/legacy ctors 优先级排序；共享于 G3 loader 与 G4 C++ SDK |

`tasks.cpp` 的 wait/cleanup/exec 修改已按上述共享契约汇合。没有添加重复的
glibc PID 完成缓存、第二套文件 RPC 序号或另一种 loader ABI。网络服务加固与
网络客体仍在 PR155/158/162 的专项链路中；本分支只复用通用 IPC 机制。

具体来源为本地进程基底 `18fb9d0`，追加 PR157 等价提交 `9110ecc`、`db724a0`，
以及 PR161 等价提交 `05809a3`、文档收口 `5c8fb79`。远端分支通过多父提交关联
已经完整合入的 PR156/157/161；通用 IPC 的窄变更单列来源，避免把尚未合入的
网络用户态源码误记为该合并的内容。

## 本分支实际检查

```sh
python3 tests/glibc_g3_files_host.py --output build/dependencies_file_host
python3 tests/kernel_process_wait_race_test.py --output build/dependencies_wait_host
python3 tests/kernel_exit_cleanup_gate_test.py
python3 tests/process_wait_acceptance_host.py --output build/dependencies_wait_identity
python3 scripts/verify_evidence_index.py docs/reports/glibc_g3_dependencies_20261125/manifest.json
```

文件状态机47项、真实files/FatFs14组、内核wait8项、身份/源码控制8项和实际
sys51降级控制均通过。宿主测试模拟各自的内核/服务传输边界；所执行生产实现
与输入摘要见公开报告。已有各专项客体报告保持原源码/SDK/镜像绑定。

出站 spawn/exec/fork 实现在后续独立 PR 增量提交。本共同基底尚未单独运行
QEMU 客体；包含进程、文件、终端和 C++ 的成套 SDK/系统由 G3 组合里程碑
提供新的实际客体结果。来源和 ABI 细节以对应专项契约为准。
