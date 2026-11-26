# 4939fb8a · Mobius 和 ClarkE 的产品标识

2026-11-26。Mobius 用于两套现有桌面入口的应用标识；ClarkE 用于浏览器应用、
窗口和标题。单 Surface 会话优先请求 `/bin/mobius.elf` 和 `/bin/clarke.elf`，
旧工作盘在正式文件缺失时可继续使用旧入口。产品名、包 ID 规划和共享 Aurora
库的边界记录在 [产品标识契约](../contracts/product_names.md)。

用先前实际构建的 Qt 6.8.3 Widgets 和匹配线程 SDK，重新构建了 ClarkE、Mobius
单 Surface 程序与会话父进程。QEMU 11.1.2 的会话夹具验证正式路径优先、旧盘回退，
两个场景都启动子程序、恢复桌面并恢复资源基线。新 ClarkE 的交互本地页 10 项、
受控 HTTP 9 项通过。回执在私有 `build/product-naming/` 目录。

本批实现可见标识、会话入口和兼容回退。xypm 安装、包管理迁移、另一套桌面分支客体
及 Web 引擎升级需另行验收。共享的 Aurora API、资源 ID、历史报告和协议继续按原契约使用。
