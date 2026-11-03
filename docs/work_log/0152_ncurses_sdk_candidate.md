# ncursesw 组合 SDK 候选

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

`scripts/probe_ncursesw.py` 的构建报告新增公开头文件摘要；
`scripts/prepare_ncursesw_sdk.py` 校验 UTF-8 SDK、锁定源码、有效目标归档、五个公开
头、同源 xterm 数据和许可证材料，再生成私有候选：`sdk/include/ncursesw/`、
`sdk/lib/libncursesw.a`、`sdk/licenses/ncurses/` 和目标路径
`target/usr/local/share/terminfo/x/xterm`。库和头与底层单线程 SDK 绑定，应用应使用
`-I <sdk>/include/ncursesw`、`-D_XOPEN_SOURCE=700`、`-D_XOPEN_SOURCE_EXTENDED=1`
及静态链接组；示例命令见 `tests/ncurses_sdk_candidate_smoke.py`。该数据必须放入目标
同一路径；不支持任意终端数据库、动态尺寸或线程 profile。

最终候选 `${XOS_SCRATCH}/xos_ncurses_sdk_delivery_v4_20261101` 树 SHA-256
`1e8ce23536b70e19320e0b4e7b0e7529851309f667fa98ea7fd8d1e4833a1317`；base SDK 树
`dac99ae40c67299e6173431829fd21ba03663b74195d1f28bf4e46cbbadf6b78`，目标库
`737fc1d7df0ff882095edd2232a6b053109107ab61023dd98c38469b93b613cd`，terminfo
`588f74f5a9a0500697a23f8074e22ab683346bd2f62db17324ffc77f223fe1f9`。四个独立
消费者仅使用此组合 SDK 交叉链接成功；宽字符 ELF 约 1.6 MiB，库约 864 KiB，
运行时峰值尚未测量。`tests/ncurses_guest_probe.py --composed` 将验证组合回执、消费者
和目标数据并运行客体；尚未在提交后的快照执行。

更新许可证事实登记，候选保留 upstream COPYING 与源码锁；逐成员审查、静态分发和
正式发行资格仍未完成。更新登记后旧 build 的许可证检查因复制版本不匹配而失败；
新系统 build `1ea082222ecb7fd6` 的 `python3 scripts/license_audit.py --build
build/w2_sdk_composed_20261101` 通过 7 份材料检查，不等于逐成员法律审查。
该候选状态为 built_unverified；完整 W1/W2、资源、兼容和 PR 仍未完成。

提交 `ca54556` 后在干净快照重建 build `1ea082222ecb7fd6`，以组合 SDK 独立链接的
消费者及组合包内 terminfo 经正常 Xsh 运行：宽字符、重入、locale 和空闲服务故障
恢复四组通过。ISO SHA-256
`c6a4508c9eafa04976ee0ab6bb4e3013ca4536c9d0e90bf213b34c7d9e1c9919`，串口 SHA-256
`050dabcfcb7eebd2a6f3b09bbbac1d026deb34c9fd7587e24b29309d8807205d`；回执位于隔离
工作区 `build/w2_sdk_composed_ca54556/ncurses_guest_probe_report.json`。组合 SDK 仍为
候选而非正式发行，资格只覆盖该回执列明的配置与行为。
