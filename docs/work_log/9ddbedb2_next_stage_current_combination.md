# 9ddbedb2 · 当前主线常规组合复验

以主线 `9ddbedb2f944488775f14741a09b5f5988c31e9a` 的 Git 归档作为构建输入。
该提交已包含 glibc 显式应用 SDK 与共享 PIC 归档构建修正、Pumpkin 开发配置的
跨重启登录、ClarkE 目标 JSC 配置与受控 TLS 纵切片。复验的对象为普通 XOS 镜像。

在 Linux arm64 用锁定的 x86-64 交叉工具重新构建，显式提供锁定的 lwIP 归档。
容器 QEMU 11.1.3 在 kernel smoke 被项目版本检查拒绝。把同源重建的整个
`build/` 复制到隔离测试工作区，使用锁定的 macOS QEMU 11.1.2 重跑。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$archive" python3 scripts/build.py
make -o build smoke
python3 tests/abi_doc_consistency.py
```

普通镜像 `06608c726fa0dbc5` 通过 79 项启动、内核、任务、进程、文件、持久化、
容量、libc、存储和运行时检查，并通过 10 项许可材料检查和 ABI 表检查。
本回执只覆盖上述普通镜像检查。显式 glibc SDK 和应用、专用 Pumpkin 配置、
ClarkE 完整引擎及最终发行候选仍按各自配置与组合门禁验收。

| 工件 | SHA-256 |
| --- | --- |
| 系统 manifest | `41421345b35d2ff5d099b04e403571b3fb91c0813d092d1da8edda9bfd25821c` |
| ISO | `67d61c0c150200d88bb3443372ca854ed9c4df7c43302ea3552b04ba14ca3a59` |
| smoke 原始日志 | `8a02cae526efc3b8a64b27fd5f7023e859f98ab50e097028b98e3fe5ed6f41b9` |
| ABI 原始日志 | `e2e4c52a0306922418b0917ef17cc47d9eba2bec406bbb9f4f1387b8c86eb301` |
