# 0227427a · Mobius 和原生 TLS 合入后的组合复验

从主线 `0227427a` 重建启用锁定 lwIP 的普通镜像 `6c02db296afc1ff6`。
QEMU 通过 79 项普通客体检查及 10 项许可材料审计，ABI 表核对通过。
在合并前以同一 Git 源树及相同 ISO 字节完成 8 项原生 TLS 客体回归，
包括已验证叶证书校验、会话清理与无熵启动拒绝。
[组合工件回执](../reports/next_stage_0227427_20261127/manifest.json)

重建运行 `XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" make smoke` 和
`python3 -B tests/abi_doc_consistency.py`。TLS 探针沿用专项验证的静态
glibc SDK 和源包，客体重新绑定本次 ISO 的完整系统输入。
[TLS 重跑方式及覆盖范围](514a40f2_clarke_verified_peer_leaf.md)

Mobius 的 Qt Widgets 套件使用统一 glibc SDK v1，已在前一个组合镜像通过独立
接收及复链和双 Shell 安装回归。发行 SDK v2、Net2 的 POSIX 套接字和 WebCore
全量链接仍按各自专项门禁验收。
[Mobius 专项复验](2d4bde25_mobius_unified_widgets.md)
