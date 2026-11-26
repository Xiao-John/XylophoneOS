# ab3628db · glibc 正规化路径的原生文件入口

Fontconfig 的真实目标程序拉入 GNU `realpath`，旧 SDK 因缺少内部 `__faccessat` 无法链接。
XOS 的 `faccessat` 走原生 files 会话，核对 mode 与 flags。它支持绝对路径和从当前工作目录
解析的相对路径。其它相对 dirfd 仍返回 `ENOTSUP`。在当前没有链接的命名空间内，
`readlink` 使用同一会话解析路径，对存在的非链接返回 `EINVAL`，并保留 `ENOENT`、
`ENOTDIR` 与传输错误。用真实 UID 或有效 UID 查询均取当前会话实际授权。

以签名 GNU 源重新生成 C SDK。合入包含 Pumpkin 存储租约修复的主线后，重新核对全部 SDK
构建输入摘要并重建普通镜像 `17cebdf4873d898e`。QEMU 11.1.3 通过 xsh 及 dash 各三次
现有 cwd 回归。新增断言覆盖权限与 errno、UTF-8 路径、`.` 与 `..`、缺失路径及文件后的
斜线。每次回到 129696 空闲页、3 个任务、1 个完成记录，ABI 表一致。
[源码、工件和客体回执](../reports/glibc_canonical_path_20261126/manifest.json)

这两个 libc 入口依赖普通应用已经建立的文件会话。引导阶段的 GNU 解释器路径由 D1 定义。
