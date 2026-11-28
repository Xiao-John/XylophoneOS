# xypm GHCR 合并交接

PR [#467](https://github.com/Xiao-John/XylophoneOS/pull/467) 已于 2026-11-28
合入，合并提交 `5f6b7867811d40aea6bc07834ca087911870d6a7`，被审查的
head 为 `30a35c159a039f0861ca05af00519fd428fbc18d`。本次文档提交仅更新
全局状态，复用该 PR 已公开的实现和证据，不新增或改写冻结报告。

## 已交付与范围

宿主和 glibc xypm 取得固定摘要的公开 GHCR OCI XPK，保留 bearer token
跨源隔离、流式临时文件验证和独立维护安装。主线 P1-D 认证发行入口继续存在。
实现与原验证命令见 [HTTP/GHCR 工作记录](1d93bb21_http_streaming.md)，
公开客体摘要、原数据库与平铺清单见
[验收目录](../reports/xypm_ghcr_guest_20261128/README.md)。

原客体构建 `faa268574f3d5577` 的生产代码来自 `b8851363f426129ae51cba932a2ca5403d7530ed`；
后置 head 仅增加报告和文档。这一结果绑定其实际源码、镜像、SDK、固定 IPv4
与 CA 快照。私有仓库、自动 DNS、物理断电、认证发行客体回归未运行，legacy
newlib 完整 SDK 构建仍受原记录中的输入限制。本次合并不生成新的 Release，
不将该结果转称为其他后续运行库组合的客体资格。
