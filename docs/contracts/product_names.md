# XOS 产品标识与迁移

| 产品 | 可见名称 | 正式客体入口 | xypm 包 ID |
| --- | --- | --- | --- |
| 系统 UI | Mobius | `/usr/bin/mobius.elf` | `xos.mobius` |
| 浏览器 | ClarkE | `/usr/bin/clarke.elf` | `xos.clarke` |

客体入口随产品安装。单 Surface 会话优先使用正式入口。只有文件服务确认正式入口不存在时，才试旧盘上的 `/bin/desktop.elf` 或 `/bin/browser.elf`。打开失败的其他原因及加载失败继续如实返回。通过文件名启动的程序仍使用相同的装载权限和会话生命周期。

两种包分别拥有各自安装文件。Mobius 同时安装 `/usr/bin/mobius-session.elf`，ClarkE 是可选应用，Mobius 包无需依赖它。ClarkE 管理的内置页面位于 `/usr/share/xos.clarke/web/`。浏览器仍使用 `/web/` URL，只有五个公开的内置页面与资源在旧路径缺失时使用包内副本。

用 [候选打包脚本](../../scripts/package_desktop_products.py) 在指定线程 SDK 和 xypm profile
下生成私有开发包，脚本验证 ELF、构建回执及 SDK 树。候选包的安装、升级、卸载和客体
证据见 [产品包记录](../work_log/af27a498_desktop_product_packages.md)。发行时按实际 Qt
与 SDK 组合另行复核许可和重链接材料。旧盘用户文件沿用现有归属，迁移不得覆盖同名用户文件。

Aurora 仍指共享视觉库、历史设计或既有协议。保留共享的 `aurora` 命名空间、`libXosAurora.a`、资源路径、服务名称和冻结证据。源码目录的历史名称可与发行入口并存。笔记应用沿用自己的标识。

[阶段计划](../plans/next_stage.md) · [ClarkE 本地与 HTTP 运行契约](aurora_browser.md) · [Mobius 单 Surface 会话](../../src/ports/aurora_desktop/README.md)
