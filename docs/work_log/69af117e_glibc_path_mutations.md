# 69af117e · glibc 路径变更

2026-11-26 · 存量 sbase 工具的 glibc profile 核验发现 SDK 仍含 `mkdir` stub。
从进程复验合入后的 `db8e15dd` 开始，接入 `mkdir`、`rename` 和 `rmdir`。
`rmdir` 在 files 同一次请求内确认目录类型和空目录状态，以免在客户端判断后
误删普通文件。ABI 分配与旧服务行为见 [路径变更契约](../contracts/glibc_files_v1.md)。

从 `da7f1d2f` 的源码和签名 glibc 2.44 归档构建 C SDK 与正常系统。带
`directories` 的候选 profile 通过完整 SDK 核验。QEMU 11.1.3 三次独立运行
通过普通 xsh 入口，均退出 0 并恢复资源基线。用例涵盖相对路径、重复目录、非空
目录、普通文件拒绝、跨父目录重命名、源缺失、精确字节和清理。另通过当前 ABI 表
一致性检查。完整 daily utilities 的管道和外部命令重定向单独验收。

```sh
python3 tests/glibc_static_guest.py --system-build "$XOS_SYSTEM_BUILD" \
  --glibc-build "$XOS_GLIBC_SDK_BUILD" --suite path-mutations --repetitions 3 \
  --output build/glibc_path_mutations
python3 tests/abi_doc_consistency.py
```

| 工件 | SHA-256 |
| --- | --- |
| 系统 `7a6b2533dead9800` manifest | `ea5041d4214b1677362049133100ba7ca77caed6aca963eeda282c2a89b172c6` |
| ISO | `9af1dee98b01b681ec7f0d3e7e80aa51ad33b2ddcaf630274fbd3c1ae88729b5` |
| glibc C SDK manifest | `74cb7ddcc19240d7782dfd20a82924318d1046956f4950e5da18e81a2c8dc79b` |
| directories 候选 profile | `e2aae837fdd7b6cf342f3f65af57c6d9ae292eda59e47b8ebf8d1d246237e838` |
| QEMU 报告 | `c1073338a4c3aafd2331c10957748164e8baebd825371000a5c67eed6bfb349c` |
| 串口 | `5f499e9db388e92eb6b306caf1aa66606937edeb98a59f6860b255f6b70c76bc` |
