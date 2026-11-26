# 03c0fe80 · 安装介质先完成包维护，再启动音频

基线为 `e33ef656`。安装镜像的三个成员都已暂存，但监督进程先启动了音频服务。
P2 的维护准入要求此时仅有监督进程和文件服务存活，因此返回 `-11`。该失败发生
在包管理器启动前。将普通音频启动移到安装与恢复阶段之后，保留原有维护准入、
恢复和下次启动重试规则。既有双镜像 marker 测试附带检查正常提示符出现后音频
服务已运行。

## 实际安装镜像复验

从 `03c0fe80f5aba677b6d89c15690e99480a3ce63a` 构建普通系统。使用同一批已绑定
的 glibc dash、原生 xypm 和精简版日用工具 XPK 重建安装镜像，XOSBND1 三个成员
逐字节一致。Linux arm64 宿主的 QEMU 11.1.3 在新工作盘上实测暂存、`xypm ensure`、
不可变恢复程序清理和安装完成标志。客体同步后离线检查 26 个已登记文件和三个暂存
成员的准确摘要。

```sh
python3 scripts/build_install_iso.py --build-dir "$SYSTEM_BUILD" \
    --dash-manifest "$DASH_RECEIPT" --member "3:daily=$DAILY_XPK" \
    --member "5:xypm=$XYPM_ELF" --output "$INSTALL_ISO" --manifest "$ISO_MANIFEST"
```

| 工件 | SHA-256 |
| --- | --- |
| 系统 `7226301f5cba1800` 清单 | `3ea1744d15868404fffb69019e860e0b092eb7ba61b93a8d1d1558834e131dc1` |
| XOSBND1 | `2ddc3642dd5393a93deaf5673e9da83a317faee417363f2fd095197cfc98685c` |
| 安装 ISO | `dfd05ca2877c7d956ad1d5c4a0944a96b42584c92182c777eeba04a826021a0e` |
| 安装清单 | `2b06827f66d49c05d0e076d07cece476b8f2b22887686350b56611c98c9c05c3` |
| 安装报告 | `9d0a1f5163744dc26971bed7ea1db23fc39d911e946cbaa326f3e491ea3a6b38` |
| 安装串口 | `c85ae3e39e84602586421011a08790a820c755c05596a8dbde138f7777e72512` |

## 音频与新镜像 marker 复验

同一运行时代码在 macOS 的 QEMU 11.1.2 通过 6 项普通启动检查。普通镜像使用
独立工作盘启动，`ps` 显示休眠中的音频服务 `audio_servi`，为内核任务名的显示
形式。用 `38233e84` 的 marker 测试和同源 newlib dash，在同一独立工作盘先后启动
两张携带不同 XPK 测试数据的镜像。测试专用包管理器使测试聚焦于 marker 更换与
启动顺序。两轮均完成 marker 刷新与音频启动。

| 工件 | SHA-256 |
| --- | --- |
| 普通镜像 | `de96b451418b2f45a3299add77605a366b14f33b894b17b7bbc5336fe8c18618` |
| 普通镜像音频检查串口 | `346a34168b3cf71ff8a4612d69524208e3b9015953307c1e29c69e0c4e84ae21` |
| 双镜像 marker 测试日志 | `9ce254a68f3b0ea28c32c6701d8379d50dbbacaaff01c927e50a7b4fa7bcf1b2` |
