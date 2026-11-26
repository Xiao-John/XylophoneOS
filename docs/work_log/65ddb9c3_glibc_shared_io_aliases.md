# 65ddb9c3 · glibc 共享 I/O 符号

主线 `217d3661` 的共享 libc 构建在通用 `fstatfs` 后端遇到别名错误。
glibc 的私有头文件已经为 `__fstatfs` 声明隐藏符号，通用实现缺少与之配对的
`libc_hidden_def`。补齐定义后，GNU 的普通入口、弱别名、链接警告和 `ENOSYS`
语义都保留。继续构建 `libc_pic.a` 时，首个编译错误移至 XOS 的 `lseek64`。
该实现有隐藏定义，补齐本地声明后，公开弱别名和实际的 `__xos_file_seek`
调用保持原样。

## 实构建验证

从干净源码进行两组前后对照。GNU glibc 2.44 原包均通过上游签名核验。
Linux arm64 宿主使用 XOS GCC 16.2.0 与 GNU binutils 2.47.20260726，断网构建，
分别用两个和一个构建作业。两组的 SDK 输入清单分别只有 `fstatfs` 补丁与
`sysdeps/xos/lseek64.c` 发生变化。

用 `scripts/probe_glibc_rtld.py` 生成静态和共享配置。对每种配置分别执行
`make -C "$source/io" objdir="$config" "$config/io/$object"`。改前的两个
`.os` 目标均以状态 2 复现别名错误，改后的两个真实 PIC 对象通过。附带验证
`statfs.os`、`statfs64.os` 和 `fstatfs64.os` 也可编译。`readelf` 确认两个 PIC
对象都有隐藏入口和公开弱别名。分别用 `objcopy -O binary --only-section=.text`
提取静态对象机器码，改前和改后的对应字节完全一致。
收短补丁的上下文后，分别在上游原包的两份副本应用原补丁和最终补丁，生成的
`io/fstatfs.c` 逐字节相同。

第一处修复后，由共享配置目录执行
`make -j2 -C "$config" "$config/libc_pic.a"`。在 `lseek64.os` 处返回状态 2，
随后单独复现并修复该对象。完整 `libc_pic.a` 尚未在第二处修复后复跑，完整
`ld.so` 和动态客体启动也尚未验收。

| 工件 | SHA-256 |
| --- | --- |
| 改前 `fstatfs.os` 错误日志 | `177b29b514675a838b930e64e61d185002c5473426b01bea444791126552c26a` |
| 改后 `fstatfs.os` | `3e24b44bbb753f7bdcec1e84e79034643246cc8be8048cda49fba666e46a92ef` |
| 前后相同的静态 `fstatfs` 机器码 | `d63eb10a6849af9bc5e23ed4eab674ebb0307ab397c660a00ccd84d64614e3b3` |
| `libc_pic.a` 到达 `lseek64` 的日志 | `2eb1bef656eb280c0b76cc45927fc9b5af46984aff8a84002b8a5b3998c3dcf7` |
| 改前 `lseek64.os` 错误日志 | `415bdea10a5bb3c8cce28e72cde270410daabdf0b859e43a93c05d1edb546ab4` |
| 改后 `lseek64.os` | `87cc76c0273a3b4c942c3860baf772a44220873de69e8a196d1a8206dc01b203` |
| 前后相同的静态 `lseek64` 机器码 | `d7f7f1978347429f4a7b1ac85c7428faf74be46db5732f6dde89a5263439ec30` |
