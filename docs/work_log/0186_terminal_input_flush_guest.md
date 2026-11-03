# 已排队输入的清空与新输入

2026-11-03。已有客体交接测试调用过 `TCIFLUSH` 和 `TCSAFLUSH`，但调用时没有
确认输入队列非空，不能证明已排队输入被丢弃。现扩充专用终端应用和宿主握手：
分别先发送一个字节、通过受限 select 确认可读，再调用 `TCIFLUSH` 或
`tcsetattr(TCSAFLUSH)`，要求随后立即查询不可读；再发送新字节并要求原样读取。
`TCSAFLUSH` 同时检查成功后 `VMIN/VTIME` 已更新，最后恢复原模式。

此受控场景只验证各一个已可读字节和之后的新字节，不推断硬件 FIFO 全部边界、超过
256 字节时部分丢弃、连续输入竞争或断电行为。应在提交后重建匹配的专用系统、SDK
和探针，并在 QEMU 客体上执行；若失败先调查实际路径，不以宿主模拟代替。

提交 `557b63fe09ec00ef8d140e91f57cd319c9a6ece4` 后重建专用系统，build ID
`de3622c733f8a297`；`tests/terminal_handoff_probe.py` 的 15 组客体检查通过，包括
两种清空、模式更新和清空后新输入。镜像 SHA-256
`7360d50b33d284fecae6da4e14b8e75342be8f9dff22b1378ab50bff1bc2566c`，SDK 树 SHA-256
`1b61144674104ba6da26538fc92a64b6e490a620108665239aded6f32c39effc`，串口 SHA-256
`6be7a5cfcf6ef9aff163e8b4bd61b8e070362ef5d22d1b81036b8de856e61ffb`；报告位于
`build/w1_flush_system_557b63f/`。结果保持上述单字节及受控时序边界。
