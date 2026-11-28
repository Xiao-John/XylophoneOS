# b61f0a29 · 私有 FIFO QMP 验收通道

当前 pre-release SDK 的执行环境不提供 Unix-domain socket，完整启动 smoke
又实际使用 QMP 检查 BIOS 键盘、寄存器、物理内存与截图。serial-only 案例可以
明确关闭 QMP；完整 smoke 需要保留这些检查。

`Guest` 新增显式 `XOS_QMP_TRANSPORT=pipe`，由 QEMU 原生 `pipe:` chardev
连接私有 TemporaryDirectory 内的两条 0600 FIFO。没有 socket listener。
读写均使用非阻塞 FD 和五秒绝对期限，回复上限 64 KiB。启动先完成真实 QMP
握手与状态往返，再放出已有 debugger fixture 的 ready 标记；退出关闭两端。
默认仍为 Unix transport，`qmp_enabled=False` 的串行路径不打开 FIFO。

```sh
XOS_QMP_TRANSPORT=pipe python3 tests/boot_smoke.py
XOS_QMP_TRANSPORT=pipe make -o build smoke
```

已在 SHA-256 `60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`
的 SDK Preview 2 中，用 QEMU 11.1.3 实际冷启动 BIOS 映像，通过 greeting、
capabilities、query-status、BIOS 键盘输入 help 与 screendump。
[明文回执](../reports/p0_qmp_pipe_20261127/manifest.json)保留原截图和日志摘要。
完整 smoke 尚待匹配发行候选及额外 LLVM host tools，未由上述四项代替。
该变化只改变验证通道，不改变 guest 产品 ABI、权限或测试断言。
