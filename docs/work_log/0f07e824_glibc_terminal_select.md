# 0f07e824 · glibc 终端 select

ncurses 的键序列解析需要在唯一的终端输入描述符上进行有界或无限期读就绪
等待。glibc 的该调用现在通过已授权的 terminal v2 会话使用现有
`wait_readable`。租约固定实际终端对象，已有会话交换时返回 `EBUSY`，
避免将繁忙当作空闲超时。原生中断为 `EINTR`，就绪查询保留输入字节，
单调时钟等待采用绝对时限。普通文件、多个描述符、写及异常就绪明确返回
错误。[终端接口契约](../contracts/glibc_terminal_v1.md)

从 `07422224` 的系统基础构建。实现和测试提交分别为 `0f07e824`、
`a3dcf2b1`。用两个作业重建一次签名校验过源码的 glibc 2.44 C SDK。
静态库导出真实 `__select` 与公开别名，生成的 stub 清单仍包含 `poll`、
`pselect`。业务配置和 ncurses 的验证由后续候选测试承担。

| 资格输入及回执 | SHA-256 |
| --- | --- |
| SDK manifest | `1a433be76f4a6193de70453f595f06298449f46ecdd4604c4a8c4e9d134028e8` |
| SDK 压缩包 | `b941c6b5e0039fa17685dd73b96597b00231d017efc92828f879532bde2122c4` |
| 普通系统 `2d267237ed545b7c` ISO | `72f507ea62b6f7ea4897b49dba646063beefd77a2f0dc2a4e893464ad77dcc2c` |
| 终端 probe ELF | `e2adb061953899a7f3fca09bb40ba3a8bd9d862bc6f7e630d9f5b6c3b25e1d1d` |
| 客体验收回执 | `a0996120faff9d890ba3896c464453c9dda15b3a23c7468e8bfd958f3a416378` |

宿主保留真实 FD、终端客户端和公开 `select` 实现，替换内核传输边界。
普通和 ASan/UBSan 两轮各通过 24 组，覆盖原生超时和中断、极大时限饱和、
忙会话以及请求序号。
QEMU 11.1.3 使用 `tty-run` 授予的真实终端，覆盖空输入零时限、
70 ms 空输入、有限及无限等待后收到准确字节、同一输入的别名就绪和
保留未读数据。非法及普通文件描述符返回对应错误。既有终端 I/O 与
native exec 接收器也各通过一次。三项完成后的资源基线均为
129514 页、4 个任务、2 个完成记录。
[宿主门禁](../../tests/glibc_terminal_host.py) ·
[客体门禁](../../tests/glibc_terminal_guest.py)
