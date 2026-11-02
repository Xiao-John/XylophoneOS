# ncursesw 分片输入与窗口边界探针

复核 W2 现有消费者：locale 探针覆盖 UTF-8 转换分片和非法序列；宽屏探针已有颜色、
中文和组合字符输出、方向及功能键，但终端输入未明确分片，窗口越界和局部刷新也
没有独立断言。现扩充宽屏消费者，验证窗口越界失败、宽字符单元读回和颜色属性，
通过 `wnoutrefresh`/`doupdate` 做局部更新；重入消费者验证超尺寸窗口及越界移动
失败（子窗口超出父窗口边界）。串口驱动等待方向键消费后的标记，再将中文 UTF-8 首字节与余下字节间隔发送，
并核对局部更新字节。

这是受控的 QEMU 字节流和声明 xterm profile，不验证所有真实终端模拟器、字素簇、
终端输入非法序列或动态尺寸。交叉编译通过；所有修改提交后必须重建同源组合 SDK
并在客体运行，不能以编译证明 W2 通过。

提交 `552fe6f` 后的首次客体运行中，分片输入与宽屏局部更新检查通过，但重入
消费者以代码 8 退出：探针错误地要求超屏幕的 `newwin` 返回空。核对锁定源码
`ncurses/base/lib_newwin.c`，`newwin` 允许正尺寸窗口大于屏幕，而 `derwin` 检查
子窗口是否超出父窗口。故将断言改为 `derwin` 的父窗口边界；这不是目标库修复。
首次失败的串口 SHA-256 `5ae7a8d38f22d1c974ccdc65733dcc6b244fc309b05ecae149b900c94a4991a1`，
报告位于 `build/w2_coverage_system_552fe6f/`。更正后须提交并重建、重新执行客体。

提交 `a719ee6ec0c9be4232023e6e35e28aefb8840218` 后重建系统、UTF-8 SDK、目标库、
同源 terminfo 和组合 SDK，在正常 Xsh 客体运行结果 `passed_probe`：包括中文输入
分片、窗口边界、单元读回、颜色、局部刷新、重入、locale 及既有故障恢复检查。
build ID `01ca3b195799ede0`，系统 manifest SHA-256
`ba175516bc6d2adccc40be5bb5a11cad55bcced26218b41fbb8d88fb599d3af7`，镜像 SHA-256
`33afdd8a522ce5b7a67e5d138e2fcbd0c2066fe1ddc0218999f4335c4a7d4e29`，组合 SDK 树
SHA-256 `038491cd8cefcc77551b681b3954e20983d979f7d1d32a4df7bf982bf0fd27d0`，
目标库 SHA-256 `875c1462d12187d0d31e21fb2af70a933e18c7d867ea99e7e4c1372c54aac5b0`，
terminfo SHA-256 `588f74f5a9a0500697a23f8074e22ab683346bd2f62db17324ffc77f223fe1f9`，
串口 SHA-256 `093a0c920f8be4e7d84978f20ed318a7410204481e7f06bc549e431a5b799899`；
报告位于 `build/w2_coverage_system_a719ee6/`。此前列出的未覆盖范围及 W1/W2
组合资格仍不由此通过。
