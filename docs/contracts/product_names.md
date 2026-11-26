# XOS 产品标识与迁移

| 产品 | 可见名称 | 正式客体入口 | xypm 目标包 ID |
| --- | --- | --- | --- |
| 系统 UI | Mobius | `/bin/mobius.elf` | `xos.mobius` |
| 浏览器 | ClarkE | `/bin/clarke.elf` | `xos.clarke` |

客体入口随产品安装。单 Surface 会话优先使用正式入口。只有文件服务确认正式入口不存在时，才试旧盘上的 `/bin/desktop.elf` 或 `/bin/browser.elf`。打开失败的其他原因及加载失败继续如实返回。通过文件名启动的程序仍使用相同的装载权限和会话生命周期。

xypm ID 是待实施的包登记。打包时须为两产品分开登记安装路径、所有权、精确版本依赖和卸载范围。若已有冻结发行或用户盘依赖旧入口，先在专用工作盘实测兼容与升级，再切换发行默认安装。给旧数据或包名迁移前，核对实际使用者与包数据库，禁止覆盖同名用户文件。

Aurora 仍指共享视觉库、历史设计或既有协议。保留共享的 `aurora` 命名空间、`libXosAurora.a`、资源路径、服务名称和冻结证据。源码目录的历史名称可与发行入口并存。笔记应用沿用自己的标识。

[阶段计划](../plans/next_stage.md) · [ClarkE 本地与 HTTP 运行契约](aurora_browser.md) · [Mobius 单 Surface 会话](../../src/ports/aurora_desktop/README.md)
