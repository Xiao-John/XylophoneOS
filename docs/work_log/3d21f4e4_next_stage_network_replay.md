# 3d21f4e4 · Net2 TCP 与原生 TLS 主线复验

从主线 `3d21f4e4` 分别重建带锁定 lwIP 的普通配置和受信静态网络配置。
普通镜像 `da3316b7893d87cd` 通过 8 项原生 TLS 客体检查、10 项许可
检查和 ABI 表核对。静态配置镜像 `8a1dbc18ca75a006` 通过 9 项 glibc
Net2 TCP 客体检查，其中四次实际传输跨两次 Net2 服务启动。

两个客体分别绑定各自已实编的静态 glibc SDK，测试入口与专项一致。
Net2 容器首次在构建 FAT 传输工具时遇到只读输出目录。补挂专用可写输出后，按
同一源码、SDK 和镜像重试，完成全部客体检查。此处保留两种配置的通过范围。
完整 WebCore、动态 TCP 与发行 SDK 切换仍走各自验收门。
[绑定回执](../reports/next_stage_3d21f4e4_20261127/manifest.json) ·
[受控 TLS](514a40f2_clarke_verified_peer_leaf.md) · [glibc TCP](61202e5f_glibc_net2_tcp.md)
