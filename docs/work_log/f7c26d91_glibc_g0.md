# glibc G0 与移植期纪律

2026-11-12。按用户指示在加固周期开始 glibc 来源、配置及接口勘查，并在 `docs/Discipline.md` 增加并行开发纪律。范围与证据见 [G0 记录](../plans/glibc_g0.md)、[移植工作面](../plans/glibc_port_scout.md) 和候选来源记录 `src/ports/glibc/source_lock.json`。未修改现有 ABI 或默认 SDK，未提交、推送或改动并行工作。

候选 glibc 2.44 归档与签名从 GNU 镜像下载；校验归档大小和 SHA-256、读取 tar 成员目录通过，哈希与另一索引一致。缺少签名工具及可信公钥，签名验证 NOT_RUN，来源记录仍为候选。实际 `configure --host=x86_64-unknown-xos` 在上游 config.sub 拒绝目标时退出 1，未构建、链接或运行客体。主机 make、bison 和 gawk 的检查提示还需隔离准备构建工具。

执行 `python3 -m json.tool src/ports/glibc/source_lock.json`、校验归档大小/SHA-256、`git diff --check` 和新增文档空白检查通过；这些不是 glibc 移植或许可证验收。下一步先独立验证签名和准备工具，同时在隔离目录研究目标识别/sysdeps 最小补丁；继续保留失败和未验证状态。工作区分支在勘查中多次由并行工作切换，不声称源码和 SDK 为单一冻结快照。
