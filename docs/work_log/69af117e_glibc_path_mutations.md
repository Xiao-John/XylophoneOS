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

评审复验在 files 入口补齐了 `mkdir` 和目录专用 `rmdir` 的尾斜杠。
从 `36568c6f` 重建系统，沿用已绑定的 C SDK，再次通过三次来宾运行。
创建不存在的带斜杠目录、清除空目录、拒绝普通文件与非空目录均经过实测。
ISO SHA-256 为 `cacd4eb16297edf9f1111ba0782f99b2682dd7dae76055ef0a7131e13eb95376`，
回执为 `36d950dd707a180925f05caa665512ddb98268d822bbb8037aac2cde92c239f0`。

虚拟 `/dev` 与 `/dev/null` 在目录变更时沿用现有虚拟命名空间。首次复验
在 `805d0237a18c3de2` 上检查了虚拟节点。评审确认空 FAT `dev` 目录误放在
服务退出测试的工作盘，同时该测试读了未绑定的 `args`。修复后从
`befe3ff18e0339d41fa9283fbcb3773d868f642a` 重建。正确预置空 FAT `dev` 的工作盘
通过三次目录变更和资源回收验证。独立跑完 files 四次，包括专用镜像真实服务退出、
恢复资源及其余存活任务检查。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `92680efba9ec1c2c` 清单 | `2027e72ea3b7b85c868926620fb19fa28afa4972f34e2506a73f4f52ed550a58` |
| ISO | `2a8b5495a9c235e801387a1f59bfda6e0dacd6f75d9a7837b96a152d02eca79f` |
| 服务退出镜像 `cc1a5f6513a4d6f2` 清单 | `90124fc53189dd56936f7bc9dcd37ccd05dd7462728a3d47ecc53b97da739ba9` |
| 目录变更报告 | `6463d2c653957c998ffcd39ded65ec48aa9a44a63ee580de2093abc721f9d085` |
| files 含服务退出报告 | `488148fcb31c4ad2a16b23be6c2efc9eb802c33eedfa2d70dea55f3780f3fc86` |
