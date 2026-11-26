# 4d6f124f · Qt Quick 接收者安装、替换和回退

2026-11-27。Qt 6.8.3 外部示例用既有离线材料原样重链接，并另用
[#308 官方 Qt Declarative 原档重编](7d5f052e_qt_quick_verified_release_sources.md)
的 QtQml、QtQuick 两个归档重链接。原样与双替换 ELF 分别为
`fefc6355…`、`bedd3609…`。新打包入口核对材料、回执、完整 SDK profile 和
静态 ELF，再通过现有 xypm v1 打包器生成修订 0 与 1。安装入口固定为
`/usr/bin/qt-quick-example.elf`。每包有 71 个文件，其中 69 个为应用、Qt 及运行库声明。
离线 Linux arm64 用 Python 3.14.10 重打，两份 XPK 与 macOS 打包逐字节相同。

## 实际流程

按照[接收者命令](../../src/ports/qt6/quick/release_materials.md#安装替换与回退示例)
从空 FAT32 工作盘执行正常 xypm 离线安装，再在新镜像冷启，通过 Xsh 加载已安装 ELF。
停止虚机，用双替换 XPK 导出新的升级盘并冷启。升级后把一个接收者文件写入该盘。
以卸载、原包装回导出新盘，保留升级后写入的用户文件，再冷启旧应用。每一步用 xypm
读回包数据库和全部受管理文件，单独导出并比对已安装 ELF 字节。卸载后确认包数据库无此
应用，受管理 ELF 已删除。

在 `4d6f124f` 及含当前主线 `1adaa908` 的精确组合 `a7c39b86` 上分别以锁定的 lwIP
归档新建普通镜像，再使用宿主 QEMU 11.1.2 TCG 串行运行同一验收。镜像分别为
`548bdc791b5af8c3` 与 `562c7f0ff8d670d1`。旧组合和当前组合分别保留证据。
保留库替换后的工作盘，使用全新导出盘完成回退，且三次冷启均按同一目标 profile 运行。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 -B scripts/build.py --output-dir "$SYSTEM"
python3 -B tests/qt6_quick_receiver_install_guest.py --system "$SYSTEM" --profile "$PROFILE" \
  --reference-package "$ORIGINAL" --reference-sha256 "$ORIGINAL_SHA256" \
  --replacement-package "$REPLACEMENT" --replacement-sha256 "$REPLACEMENT_SHA256" \
  --output "$RECEIPT"
python3 -B tests/abi_doc_consistency.py
```

两套镜像的 6 次启动均从安装路径加载程序，800×600 真实画面各有 475 个文字亮像素，
全部 QMP 画面逐字节相同。进程均退出 0，应用关闭后恢复 `121620 / 5 / 3`，图形服务
停止后恢复 `129696 / 3 / 1`。回退盘原版 ELF 恢复原摘要，接收者文件读回一致。
另核对错误材料摘要、错套件回执、错 ELF 及另一运行库 profile 均在安装前拒绝。
ABI 对照通过。

本轮范围为开发套件示例的离线安装、替换与回退。发行渠道、成品许可与产品安装信息
仍按实际发布形态审定。
[源、包、两套客体及画面证据](../reports/qt_quick_receiver_install_20261127/manifest.json)
