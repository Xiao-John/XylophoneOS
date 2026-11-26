# e9b3fe3e · glibc 共享 open 和 ttyname_r 别名

从 `4205015a` 的 x86-64 版本基线继续构建 `libc_pic.a`。GNU 真实共享编译
报告 `__open` 与 `open` 缺少 `__libc_open` 别名目标。glibc 私有头已声明
隐藏入口。为现有 XOS `__libc_open` 补齐隐藏定义，保留 `__open`、公开弱别名
和真实 `__xos_file_open` 调用。

续编通过该对象，推进到上游通用 `ttyname_r` 的相同错误。`__ttyname_r`
已在内部头声明隐藏入口。补齐定义后保留弱别名、链接提示及 `ENOSYS` 行为。
终端路径查询仍需实际实现和资格验证。

## 构建验收

Linux arm64 下以 GCC 16.2.0、binutils 2.47 从签名核验的 GNU glibc 2.44
生成静态及共享配置。分别从干净输入构建 `io/open.os`、`io/open64.os`、
`io/openat.os`、`io/openat64.os` 和 `io/ttyname_r.os`。`readelf` 确认
`__GI___libc_open`、`__GI___open`、`__GI___ttyname_r` 与公开弱别名。
两处改动的静态 `.text` 均与各自的改前对象逐字节一致。

第一次续编前比对两次已核验源输入清单，差异只有 `sysdeps/xos/open.c`。
沿用此前保留的真实共享构建目录，将单个源码覆盖为已核对摘要的版本，再执行
`make -j1 -C "$SHARED" "$SHARED/libc_pic.a"`。该轮返回 2，首个诊断已
推进到 `ttyname_r.os`。对应单个共享对象修复后的构建通过。完整解释器和动态
客体启动仍各有独立验收。

| 工件 | SHA-256 |
| --- | --- |
| `open.os` | `67e243f4f4709c276242162bc01a9d5bafedce14287ce41e8f737b38f4eb81f0` |
| 前后相同的静态 `open` 代码 | `a7586a0c5a0a917f89fde71924ca20ca2c8306a5de681915026e67cecefe90a0` |
| 首次续编日志 | `a957a49102b658cc55bf8f0e1909fd86d74cecbfe8f4fee8348f5652a93cfe51` |
| `ttyname_r.os` | `9f9669c3d980825848d0a351c6043791cce298953d168b95d64a3542cf1cea16` |
| 前后相同的静态 `ttyname_r` 代码 | `646a3700de58babe9848da64d6e9a2ff1bdbae459295428e24f19998f34455d9` |
