<!-- coderabbit-ai-generated:v1 -->

# 网络计划与 TCP 客体测试审查修复

2026-11-14；基于 `feed24ea92e4e3d001ad9b92beaff445ca4c4ee3`。

三条意见经当前源码核对均有效，已修复：

- `docs/plans/network_development.md` 将原状态明确标为基线，单列既有 N1 受限通过结论并链接原验收报告，保留 UDP 未验。
- N1 路径改为客体连接 QEMU user networking 的 `10.0.2.2`、宿主临时端口监听；保留其他范围和约束。
- `tests/lwip_tcp_guest.py` 保留预先绑定的监听套接字，将 `worker.start()` 移至网络就绪、资源快照后及首次探针前；`serve` 请求接收与挑战发送逻辑未变。

验证（Ubuntu 26.04.1 / Python 3.14.4）：`python3 /tmp/check_tcp_review.py` 通过，覆盖 Python 解析、启动顺序及提取原 `serve` 后的真实宿主套接字请求、32 字节挑战与双向 EOF；`git diff --check` 通过。临时检查脚本是本次验证工具，不作为冻结客体证据。

完整客体回归未运行：当前无 build 产物，PATH 缺 QEMU、x86_64-elf-gcc 和 NASM。原 N1 报告属于历史验收，本次未重新验收 TCP 客体。后续在准备好的构建环境按原报告命令运行客体回归；UDP 等能力边界不变。
