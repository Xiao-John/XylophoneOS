# e25a5ee2 · glibc 安装候选的应用组合

以含 GNU Make 4.4.1 的主线 `8b79200c` 在断网 Linux arm64 容器重建显式 glibc
安装候选 `e6a349fa12ec0a89`。静态 C/C++ SDK、候选 dash 和 GNU Make 绑定同一
SDK 清单和 profile。安装器本身通过五项真实客体检查。

在普通固定 QEMU 11.1.2 上，两个已由该 SDK 构建的 XPK 以 `xypm install --offline`
安装至同一新工作盘。GNU Make 以同 SDK 的已验收 ELF 导入。第一次启动从 ISO 安装
真实 glibc dash。它在同一脚本中运行 C、运行带线程及异常的 C++，再运行 GNU Make 的
直接执行和 shell 配方。第二次从同一已安装工作盘启动并重跑同组。两次均成功，
四个演示任务由启动流程自动回收，资源稳定于 `128867 / 3 / 1`。客体退出后读回
dash、GNU Make 和原用户文件，摘要均一致。
[镜像、包和客体回执](../reports/glibc_selected_app_matrix_20261126/manifest.json)

初次跨宿主重跑暴露了已单独修复的离线 FAT 工具缓存错误。随后一份测试配方把
`printf` 当作外部命令，安装盘没有该工具，GNU Make 如实报缺失。正式回放用需经
shell 的语法调用 dash 内建 `printf`，同时保留单独的直接 C 配方。

本次验收的应用配置仍须显式选择。原生 xypm 包事务、CPython、Qt 和冻结 newlib
恢复各有验收入口。GNU Make 的递归 jobserver 和发布包资格仍按专项计划推进。

```sh
python3 tests/glibc_selected_app_matrix_guest.py --candidate "$CANDIDATE" \
  --sdk-kit "$GLIBC_KIT" --c-xpk "$C_XPK" --cxx-xpk "$CXX_XPK" \
  --make-manifest "$GNU_MAKE_MANIFEST" --output "$OUTPUT"
```

## 包构建回执审查复验

测试以 `a73f568c` 对两个实际包分别校验包内声明的构建回执。回执必须绑定
候选 SDK manifest、完整 SDK 树和 profile，测试报告保留包与回执摘要。给出错配
SDK 摘要时在离线安装前拒绝。把两个包分别放在不同目录并都命名为 `app.xpk` 后，
同一安装镜像重新通过两次启动、两组应用及 FAT 读回。
[审查复验回执](../reports/glibc_selected_app_matrix_receipts_20261126/manifest.json)
