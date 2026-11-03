# Xsh 空闲终端故障恢复

Xsh 输入读取发现桥接 unavailable 时，限速尝试现有受限服务重连；成功后丢弃当前
未完成输入并重新显示提示符。若旧服务仍未退出、资源不可用或恢复失败，则继续等待，
不会回退可能已失效的旧串口，也不会重放不确定的 I/O；长期失败仍缺带外救援。
桥接输出现在循环处理服务短写，遇错只报告已确认字节并标记 unavailable，避免 Xsh
原有一次写调用截断输出。

宿主 bridge 模拟覆盖分片写和既有重连检查；正常 supervisor 构建
`build/w1_xsh_recovery_20261101` 通过，build ID `0f2ed776bc7d18e7`。扩展真实 Xsh
探针准备使用 `ps` 找到服务、`kill` 故障注入，再检查自动重连和新应用。源码提交后
才运行客体；以上不是故障恢复验收。应用在途时的真实 Xsh、旧程序兼容、前台取消和
长期故障救援尚未解决。

提交 `e361629` 后在干净快照重建 build `0f2ed776bc7d18e7` 并运行正常 Xsh 客体探针：
三项原有前台检查通过；通过 `ps` 找到终端服务并由 Xsh `kill`，shell 显示重启及丢弃
未完成输入，再运行 locale 应用并确认退出码 0。ISO SHA-256
`fb4a8318191d2b8e9face1a1d3be19dbe20a0df2e06670f745265c69965daeff`，串口 SHA-256
`0d060c0f02298d07ccb06aa59448ff9171a363711da85ca08cadba070d50350a`；回执位于隔离
工作区 `build/w1_xsh_recovery_e361629/ncurses_guest_probe_report.json`。只覆盖空闲
shell 下的可终止服务故障，不覆盖卡住的活服务、应用在途或长期不可恢复故障。
