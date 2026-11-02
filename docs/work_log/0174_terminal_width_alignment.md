# 终端字符宽度一致性：探查与实施计划

2026-11-02。W1 的 Xsh 和文件行编辑器通过 `xos::text::width` 计算列数；W2 的
ncursesw 消费者在 `C.UTF-8` 使用 newlib `wcwidth`。前者是手写近似区间：例如
U+05B0 计算为 1 列、U+231A 为 1 列，而本项目锁定的 newlib 数据分别给出 0、2。
这会影响光标回退和擦除，已有 ASCII、中文与 U+0301 的探针不足以发现差异。

选型：以 newlib 4.6.0.20260123 锁定源码及其 `combining.t`、`wide.t` 为数据来源，
将普通 UTF-8 locale 的区间供 freestanding 用户态代码复用；不让 Xsh 链接整个 libc，
也不依赖构建时联网或本地缓存。newlib 的 UTF-8 默认模糊宽度为单列；CJK locale 的
`@cjkwide`、`@cjksingle` 模式不属于本项一致性声明。保留上游许可与来源、文件哈希，
检查所有 SDK 和 xypm 的头文件复制及缓存键，避免产生缺头或使用旧数据的构建。

实施后需比较整套有效码点与固定上游数据的规则，并扩充客体对代表性组合符、宽字符
和既有中文的检查；提交之后从实际源码重建并绑定系统、SDK 和探针，再运行相应客体
回归。表文件未标明 Unicode 数据版本，不能把 `wcwidth.c` 注释中的历史 Unicode 5.0
误认为现有表的版本；以来源压缩包和表哈希标识。该工作不承诺字素簇、emoji 展示、
所有宿主终端的宽度一致，也不改变控制字符输入策略。新表来源许可和最终产物成员许可
须按实际材料核实，现有材料检查不能替代逐成员审计。

实施记录：区间从锁定源码提取到独立头文件，保留 `wcwidth.c` 中的许可声明；
xypm 的源包和缓存键均纳入该头文件。`tests/unicode_width_consistency.py` 对压缩包
和表先校验 SHA-256，再将宿主编译的实际宽度函数与上游表对所有有效可打印码点逐一
比较，结果通过。这只是宿主数据一致性检查，不是客体验收。

提交 `6f2be7dfb60222c66bf3ebb2ee9082e1f45b2ed4` 后从源码重建，系统 build ID
`67dafd3f9ce172b0`。U0/U1 客体测试通过，包括 U+05B0 零列退格、U+231A 双列
退格及既有 UTF-8 检查；报告为 `build/utf8_text_report.json`。同提交 W1 的 tty_exec、
channel、wait、device、pio、irq 分别取得 `passed_subset`，不能推断报告列出的未运行
竞争和压力项通过。重建后的 ncursesw 组合 SDK 及两个独立消费者在正常 Xsh 下取得
`passed_probe`，并冻结为 `guest_verified_subset`，位于
`build/w2_width_frozen_6f2be7d/`，树 SHA-256
`2adad2f07d82751e710986ad340089de4166fc9156f47e24e5f57cdc08a6cca9`；串口 SHA-256
`4465db440db8e9fd90081f50bea70e4ec55a28cc849545704438518a559cf40c`。xypm 使用已登记
SDK 的重新打包成功，尚未就此包执行客体测试。许可证材料核查通过，newlib/ncurses
逐成员许可审查尚未完成；以上均不构成完整 W1/W2 验收。
