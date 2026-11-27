# 458f4933 · 串行配方 CPython XPK 客体验收

从已核对的组件对应归档和冻结 v2 SDK，在断网 Linux 以合入的串行配方第三次
重建 CPython XPK。实物 SHA-256 为
`24791dcffe72bb428c8b8886be4d1325114f2c571014f52139e204629019740b`。
构建使用 `--source-date-epoch 1795759570 --make-jobs 1`，CLI 回执与原始
构建日志的摘要对应前两次重建。
[构建配方和双接收证据](cf828683_glibc_v2_cpython_receiver.md)

本次客体采用冻结候选源 `8e66789c` 的 `ce681c073de3d6c4` 系统，同一套普通 ISO、
安装 ISO、Dash、daily 与原生 xypm。测试读取系统清单记录的全部 2,026 个源
文件并逐项复核摘要。SDK 和 v2 profile 沿用冻结发行。普通 QEMU 从空白 FAT32 盘
开始，复用 `tests/cpython_glibc_xpk_guest.py`，通过七项检查。

- 安装器启动并自动装好 stock 软件。宿主拒绝把新包交给冻结 newlib profile。
- 普通启动拒绝绕过维护租约写入。持有租约时，xypm 按精确摘要安装并清理事务。
  离线读回包状态、实装 SHA-256 与 15 个归属文件。
- 冷启执行磁盘标准库、时钟与线程，检查缺失模块退出码，以及 zlib、gzip、
  deflate ZIP、zipimport、截断和校验错误。卸载后确认归属与事务文件已清理，
  原用户文件、gzip 和 ZIP 内容仍可读。

另从首次 stock 安装后的同一摘要快照开始，将冻结 XPK 安装到独立测试盘。
两份实际包的 ID、profile、上游版本和 revision 均一致。使用原生显式
`upgrade` 将旧摘要替换为新摘要，再冷启运行 zlib 用例并卸载。客体
`xypm info xos.cpython` 和离线状态分别核对两份实际包的 SHA-256，并确认
卸载状态。三次启动的检查均回到 `129806 / 2 / 0`，daily 与用户文件读回通过。
这条测试记录同为 3.14.9-r1 的显式包替换。

## 复跑

将冻结候选的实际源与已验镜像绑定在同一接收树。以下变量分别指向该
候选、发布 SDK、上述新 XPK、对应 CLI 构建目录和 stock xypm 构建回执。

```sh
python3 -B tests/cpython_glibc_xpk_guest.py \
  --system-build "$CANDIDATE/system" --stock-candidate "$CANDIDATE" \
  --sdk "$KIT/sdk" --profile "$KIT/profile.json" --package "$CPYTHON_XPK" \
  --cpython-build "$CPYTHON_BUILD" --xypm-build "$XYPM_BUILD" --output "$EVIDENCE"
```

在 `stock-installed.img` 的测试副本导入两份包。依次通过
`maint-run /usr/bin/xypm install /out/frozen-cpython.xpk --sha256 "$FROZEN_SHA"` 和
`maint-run /usr/bin/xypm upgrade /out/cpython.xpk --sha256 "$NEW_SHA"` 提交并检查
`xypm info xos.cpython`。随后冷启动执行
`exec-file /usr/bin/python3 -B /tests/zlib.py`，以
`maint-run /usr/bin/xypm remove xos.cpython` 清理，核对用户文件、daily 和事务目录。

本轮工作盘均为容器内存盘。宿主保留一份新包及回执，合计约 20 MiB。
[原始客体回执及串口记录](../reports/glibc_v2_cpython_stock_guest_20261127/manifest.json)
