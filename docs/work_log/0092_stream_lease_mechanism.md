# 0092：独占字节流读取权机制

2026-10-29。在 0091 本地认领后实现 sys80 `sys_stream_lease`：真实 supervisor 可
显式 claim console stdin 的读取权；持有者可委派给内核校验 parent 和 completion 的
直接子进程；链成员可回收/查询。旧 sys_read、sys_handle_read 和 sys54 console 等待
均检查同一持有者，委派/回收唤醒失权的等待者。成功 exec 保留进程身份，fork 子代
默认不获权；退出、fault、kill、abort、关闭 stdin 或父进程将受控子代 stdin 重定向
到非 console 时撤销相应链及后代。根失效时 fail closed；队列不随委派清空。
激活后旧内核 Escape 取消停用；默认未 claim 的兼容路径保持。此时用户态终端服务、
模式/回显、退出后的旧模式恢复和救援入口均未实现，不能宣称终端或 W1 完成。

通用机制定义在 `src/kernel/core/stream_lease.hpp`，由内核验证进程关系后使用；
单核和不可抢占区间为当前假设。持有者最多 8 层，拒绝重复；线程 SDK 和普通 SDK 的
manifest 均标 `implemented_unqualified`。sys80 已从本分支 claimed 移至 allocated，
本地登记未与其他分支同步；编号及语义仍须整合前核冲突。

宿主 `stream_lease_test.cpp` 检查 claim、重复/非持有者拒绝、嵌套委派、祖先回收、
持有者退回、祖先死亡截断、深度上限及根死亡 fail-closed；clang++ 宿主测试通过，
同源码 x86_64-elf 交叉编译通过。系统 `python3 scripts/build.py --output-dir
build/w1_stream_lease_final_20261029` 成功，提交前 build ID `9849d6a60d87da20`。
`tests/docs_consistency.py`（463 链接、67 syscall、73 历史来源）、
`tests/abi_doc_consistency.py` 和许可材料检查均通过；许可检查不等于逐成员审计。
此前宿主编译第一次因缺少内核头搜索目录失败，补齐 `-I src/kernel/include` 后通过。

没有运行 guest。上述主机测试只测纯状态容器，不证明内核进程认证、所有读取路径、
中断竞态、退出与故障、fork/exec 或资源恢复。须实现真实用户态服务与控制协议、
扩充客体测试，全部相关变更提交后在匹配系统验收，再完成 W2。
