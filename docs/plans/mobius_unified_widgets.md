# Mobius 的统一 glibc 接收方与 XPK

正式 Mobius 继续使用现有 Qt Widgets 桌面和 Aurora 共享组件，以
`xos.mobius`、`/usr/bin/mobius.elf` 和 `/usr/bin/mobius-session.elf`
交付。本阶段 Qt Quick 与 Widgets 各用独立目标前缀。统一 glibc C/C++ SDK、
锁定 QtBase 源码与 Linux arm64 生成器按实际摘要共用。Qt Quick 套件里的
目标归档按其原配置独立保留。

## 实施与分工

1. Qt/Mobius 线从统一 SDK 建立启用 Widgets 的 QtBase 目标前缀，绑定源锁、
   补丁、构建配置、归档和宿主生成器。允许复用同 SDK、同输入的构建对象，
   启用 Widgets 后由构建图重新执行受影响步骤。
2. Qt/Mobius 线在独立 Linux arm64 接收环境解开前缀，核查完整目标树和统一
   SDK，再构建现有桌面与会话。原 Qt 源树和原构建目录留在发布端。现有产品
   打包器核对正式路径、许可和实际接收方回执。
3. 客体验收先绑定普通镜像和同一 profile 的原包及升级包，再在复制的 FAT
   工作盘逐次安装、升级、回退。逐项读回管理文件，检查工作盘用户数据和
   原始盘。Xsh 和 Dash 启动已安装桌面，同时验证显式授权的原生会话入口。
   取实际 PS/2、VGA、干净退出和进程/服务资源复原证据。
4. 旧 profile 与统一 profile 的盘按现有 xypm 单 profile 契约隔离。
   单独记录旧盘处理和同 profile 产品升级。已冻结的安装数据、回执和原件
   继续保留，发行材料按本次实际成员与链接输入核实。

公共 SDK 更新独立推进。若以已有统一 SDK 套件完成首轮，本轮证据记录其
具体 SDK、Qt 源与系统组合摘要。后续 SDK 的资格由对应构建和客体验收确认。
