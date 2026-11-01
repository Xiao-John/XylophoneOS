# 0139：受限 termios 与 ncurses 编译探针

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

**2026-10-30 更正：**本记录中的 make 退出 0 仅证明对象编译完成；当时错误地使用
宿主 `ar/ranlib`，所记 96 字节 `libncursesw.a` 只有空索引，没有 ncurses 目标对象，
不能算有效静态库。原因、修复和新的严格 UTF-8 组合证据见[0142](0142_ncurses_target_archive.md)。

2026-10-30。新增自有 `termios.h` 和单线程 libc 映射：`tcgetattr` 从服务查询模式，
`tcsetattr(TCSANOW)` 仅接受固定 115200 8N1 和已实现的无回显非规范 VMIN/VTIME
子集；普通终端 read 使用服务的 `read_mode`。不支持的设置及 `TCSADRAIN`、
`TCSAFLUSH`、`tcdrain`、`tcflush` 明确返回 ENOTSUP，其他文件描述符返回 ENOTTY，
不伪称排空或清空成功。细节见[终端契约](../contracts/terminal_control.md)。探针应用
新增模式查询、更改、无数据立即读及不支持路径断言，尚未在客体运行。

`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_termios_v3_20261030` 通过，build ID `ed4d26731ba50772`，探针应用 ELF
SHA-256 `59eb4918841ff4ad9aef34c760d150cde32cc81c45709cfdf61431847a4ef578`；
多线程配置的 libc 源文件也单独交叉编译，未运行。构建早于文档更新。

锁定 ncurses 6.5 的交叉探针先在旧参数下遇到未暴露的 `wcwidth` 声明；显式指定
`_XOPEN_SOURCE=700` 后暴露标准 baud 符号和 `tcflush` 缺口，分别补充常量和明确
返回 ENOTSUP 的接口。命令：`python3 scripts/probe_ncursesw.py --archive
.cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz --sdk build/w1_termios_v3_20261030/sdk
--output ${XOS_SCRATCH}/xos_ncurses_termios_v3_20261030 --xopen-source 700 --no-sigwinch --build`。
configure 与 make 均退出 0，生成 `libncursesw.a` SHA-256
`48abd3d950484d192c0c8ab41f37cfe5f2cda000eae0b1260de167dc85bfdaa7`，报告与日志在
该临时目录。这里仅是交叉编译探针：输入 SDK 的 `_MB_CAPABLE` 关闭，未链接独立
消费者、生成 terminfo 或客体验证；配置中禁用 SIGWINCH 也不代表尺寸变化已实现。
而 ncurses 的 `TCSADRAIN` 目前明确失败，因此不能声称它可运行或 W2 完成。

下一步实现真实发送排空和输入清空，接入严格 UTF-8 SDK 和独立消费者；再完成会话
生命周期、前台切换与故障恢复，全部相关改动提交后执行客体验收。
