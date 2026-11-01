# ncurses 与 locale 客体覆盖扩展

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

在既有双消费者之外加入独立 locale 应用，检查 UTF-8 分片、非法序列、代理码点、
ASCII/组合字符/CJK 宽度及非 BMP 往返；屏幕消费者增加组合字符输出、空输入超时和
F1，保留左方向键、中文和颜色。专用 supervisor 输出两位数退出码以定位失败。
匹配 xterm terminfo 的左键和 F1 序列经同源 `infocmp` 确认为 `ESC O D`、`ESC O P`。

三个应用使用 `${XOS_SCRATCH}/xos_select_utf8_sdk_v3_20261101` 和
`${XOS_SCRATCH}/xos_ncurses_select_v3_20261101` 交叉链接，输出
`${XOS_SCRATCH}/xos_ncurses_extended_consumers_20261101`；专用系统构建
`python3 scripts/build.py --ncurses-supervisor-probe --output-dir
build/w2_extended_20261101` 通过，build ID `19b1949e763eb693`。Python 编译和
差异空白检查通过。这些只是构建证据，相关修改提交后须重新运行真实客体。
前台集成、故障恢复、竞争和资源基线仍未完成，不以新增探针替代完整 W1/W2 验收。

提交 `6002046` 后在干净快照重新构建系统 `19b1949e763eb693` 并运行客体探针，
三个限定检查组通过；ISO SHA-256
`70c88b758b89524c7ad5d8e2520a6ff6e5c090e87e30d05eb1c6c9b63bfbf4da`，
串口 SHA-256 `35c9c658bb67602a1421dd390330d705c2e770c39e00ed30242b6503f6bf957b`。
回执位于隔离工作区 `build/w2_extended_6002046/ncurses_guest_probe_report.json`。
分片和非法序列由目标 locale API 的显式调用验证，不冒称终端线路上所有拆包与故障场景。
