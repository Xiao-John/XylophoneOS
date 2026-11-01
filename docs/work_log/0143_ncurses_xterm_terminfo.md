# 0143：匹配 ncurses 6.5 的 xterm terminfo 候选

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-31。新增 `scripts/build_ncursesw_terminfo.py`：校验锁定源码和上游声明，
独立构建同版本宿主 `tic` 与 `infocmp`，绑定已验证的目标库报告及配置，然后仅生成
`xterm` 数据。工具检查两个宿主程序版本、二进制 terminfo magic、数据文件、颜色、
光标定位、清屏和左方向键能力，记录工具、配置、命令及输入输出哈希；没有安装或
改写系统数据库。目标库的固定搜索位置为 `/usr/local/share/terminfo`。

首次尝试失败：宿主 macOS 自动使用十六进制目录 `78/xterm`，而目标交叉配置是
`MIXEDCASE_FILENAMES=1`、使用 `x/xterm`。脚本现验证目标配置并显式以该布局构建
宿主工具；目标 FAT 路径大小写不敏感，此处只冻结单一小写 `xterm`，不推断其他
名称不会碰撞。`xterm` 数据声明的左方向键是 application 模式的 `ESC O D`，不是
默认假设的 `ESC [ D`；真实宿主终端仍须确认。

命令：`python3 scripts/build_ncursesw_terminfo.py --archive
.cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz --target-probe
${XOS_SCRATCH}/xos_ncurses_strict_target_ar_v2_20261030 --output ${XOS_SCRATCH}/xos_ncurses_terminfo_v2_20261031
--jobs 4`。`tic` 与 `infocmp` 均为 `ncurses 6.5.20240427`，生成 `x/xterm` 3977 字节，
宿主工具链为 Apple clang 21.0.0 和 GNU Make 3.81；
magic `0x011a`，SHA-256 `588f74f5a9a0500697a23f8074e22ab683346bd2f62db17324ffc77f223fe1f9`；
绑定的目标 `libncursesw.a` SHA-256 为
`9b9be4270344e47f48f5314ee97481e3cd7757a7faf493e5b3b08c1c87f2c2de`。完整 receipt、
工具日志和 infocmp 输出在上述临时目录，结果标记 `built_guest_not_run`。

这只证明同源宿主工具可生成并解析候选数据，不证明 XOS 文件服务读取、目标库解析、
真实屏幕、输入、大小写兼容或资源预算。数据与库尚未作为发行物打包，license 材料
和两独立消费者的客体验收仍待完成；必须先完成前台/恢复和提交全部相关修改。
