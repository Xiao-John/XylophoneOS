# GNU Screen 宿主终端探针

2026-11-03。W2 既有客体探针以管道注入键序列并检查串口字节和 ncurses 单元，尚未
经过真实宿主终端模拟器。当前主机可用 GNU Screen 4.00.03，未发现 xterm 可执行文件。
初步确认 Screen 需附着到 24×80 伪终端才可输出硬拷贝；该版本硬拷贝的非 ASCII 单元
不能直接按 UTF-8 解读，但 Screen 输出到外层终端的字节保留了中文及组合符。

新增独立 `tests/ncurses_screen_guest.py`：运行原有真实 QEMU 客体探针，将读取到的
实时串口输出同时送入附着的 Screen；宽屏消费者输出局部窗口时检查 Screen 硬拷贝中局部
窗口文本，并检查 Screen 对外层 PTY 输出的中文和组合符字节，保存各自哈希。输入
仍由原探针直接发往 QEMU，不覆盖 Screen 的按键映射；外层是伪终端，不证明字体或
人眼可见字形。硬拷贝只用于 ASCII 窗口内容，不声称解码了 Screen 的中文单元。
本机 Screen 不是完整 xterm 仿真，结果只覆盖已观察的控制序列。提交后需重新构建
匹配的系统、SDK、消费者和数据，实际运行后才能记录通过或失败。

提交 `2997a67` 的首次联合运行失败：探针等到 `W2_INPUT_READY` 后才获取画面，
但串口明确显示该标记之前已有 `ESC [ H`、`ESC [ 2 J` 清屏，导致预期窗口文本已
被清除。该失败不能解释为 Screen 不兼容；失败串口 SHA-256
`b218488d5ac48897ec60e2bbe4c8a27b4241e4b19b18ac7a5ef186a4cf054cf2`。修正方案在
转发串口流遇到完整窗口标记时暂停后续转发并捕获，再恢复；提交后须重新运行。

提交 `117fa195331f0e4782a3e9564163018d90e65f71` 后重新构建系统，并由客体探针
逐项核对先前从同源输入构建的 SDK、目标库、数据及消费者哈希；客体 `passed_probe`，
Screen 检查 `passed_subset`。系统 build ID `f020c0590e32daa6`；Screen 硬拷贝
SHA-256 `66ae76a1de71042bb519f15b7764c9f2a78d53bb134fef60fed35e1d335aff6e`，外层 PTY
SHA-256 `1aa1c63682d96a1c59c91626ea68c9999624f8533fa74a809193a587a7e6fc3d`，串口
SHA-256 `1453a89e9742dde2bf6f340629bca77f1ce01c93616b56b005e4afbddca68692`；报告及
原始记录位于 `build/w2_screen_system_117fa19/`。原有受限交付冻结为
`guest_verified_subset`，位于 `build/w2_screen_frozen_117fa19/`，其树 SHA-256 为
`3c6bea8859e847d806116ac510452df67709004465e15961a3a745bd4c2e1838`；Screen 报告
和硬拷贝独立保存，未包含在该冻结树中。以上不提升为完整 W1/W2 验收。
