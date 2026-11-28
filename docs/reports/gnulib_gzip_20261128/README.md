# Issue 133：GNU gzip 与 gnulib 的 XOS/glibc 实测

2026-11-28。基线 `344655c3f2279a10c62fce5ea039c741aa6172f1`。
本组使用已发布 glibc SDK 的 Linux 开发环境，从认证源码重建独立 glibc C SDK、
GNU gzip 1.14、真实 gnulib 消费者和同 SDK 的 dash。13 个顶层客体用例通过，
并在 QEMU 退出后检查磁盘内容和双向 GNU gzip 互操作。

## 已解决的实际问题

- 默认 glibc 的 `getprogname`、宽字符类型、`fdopendir`、`lstat` 已有可用路径；
  本组使用真实生成的 gnulib 头和库验证，不再新增 newlib 类型兼容副本。
- XOS glibc 原有 `getrlimit`/`getdtablesize` 为桩，gnulib 会退到不真实的
  `INT_MAX`。现在查询实际共享 FD 表容量 32；native runtime 与查询使用同一
  私有常量。消费者实际 `dup` 到 `EMFILE`，并验证 64 位查询、无效参数、
  其他资源的 `ENOSYS` 和失败时输出不变。文件服务独立的打开描述配额仍可更早耗尽。
- GNU `config.sub` 识别真实 `x86_64-unknown-xos`。共用配置根据 SDK 桩清单
  关闭功能，清除继承的缓存答案，不伪装 Linux，也不批量注入正向 `gl_cv_*`。
- 该 gnulib 快照把缺少 `sigaction` 等价为缺少类型，并假设 Windows 风格
  `signal()` 仿真可用。共用 XOS 补丁保留 glibc 类型和可用的信号集运算；
  信号送达/屏蔽明确返回 `ENOTSUP`，消费者检查返回值及输出结构逐字节不变。
- gzip 自身显式关闭不存在的异步信号保护，使用已有完整路径回退；通过
  `NO_UTIME` 明确禁用文件系统时间戳恢复。输出投影权限必须匹配输入，无法表示
  的变更走真实失败清理。此前 named 压缩卡住的探索版本未计为成功。

## 实际验收

| 范围 | 结果 |
|---|---|
| 真实 gnulib 消费者 | 程序名、宽类型、`O_BINARY`/`S_IRWXUGO`、stat/lstat、目录 FD 所有权、32 FD 耗尽、rlimit/rlimit64、无信号失败均通过 |
| GNU gzip 基本入口 | `--version` 为 1.14，`--help` 含 XOS 限制；普通 xsh 路径启动 |
| 普通文件 | `-nk` 保留输入；`-n` 压缩成功后删除输入；`-d` 解压成功后删除压缩输入 |
| 格式与输入错误 | CRC 损坏、截断、非 gzip、文件不存在均 exit 1 |
| dash 数据路径 | named 输入、stdin、重定向、gzip→gzip 管道和拼接 gzip members 通过 |
| 真正 gzip 写失败 | dash 传递已关闭 stdout；gzip 报 `Bad file descriptor` 并 exit 1 |
| 输出碰撞 | 已有 `.gz` 不覆盖，exit 2；原输入和既有输出逐字节保留 |
| 坏 CRC 的默认 named 解压 | `-d` 无 `-k`；exit 1，保留坏输入，删除部分输出 |
| Shell 重定向失败 | 缺失父目录时报错；这是 shell 的失败，未冒称 gzip 写错误 |
| 互操作 | GNU host gzip 1.14→XOS→原始字节；XOS 产物→GNU host gzip 与 Python gzip→原始字节；二进制样本 8496 字节 |
| 资源与用户数据 | 每个顶层用例回到 `free=129693 tasks=3 completions=1`；无关用户文件保持不变 |
| 构建拒绝门 | 篡改归档拒绝；仍缺 native 资源查询的旧 SDK 拒绝 |
| 许可材料门 | 独立材料构建后 `license_audit.py` 通过，10 份材料，登记中 open 项为 0；不替代完整二进制分发审计 |

启动的基线系统 build ID 为 `7e9d4063fa8154b7`；新 glibc 应用 SDK 与它独立
绑定。运行器核对实际 ISO/程序字节、原样 kernel/native-service 源码及构建输入，
并在结束后核对运行器依赖和工具未变。许可证材料专用构建
`df4757640f8b7ec2` 未用于客体结论，不把两个系统快照混称为同一产物。

## 来源、复现与证据

GNU gzip 原包和分离签名来自 `https://ftp.gnu.org/gnu/gzip/`；签名者
Jim Meyering 的公钥从 GNU 官方 `gnu-keyring.gpg` 提取，主指纹
`155D3FC500C834486D1EEA677FD9FCCB000BEEEE`。构建对锁定的原包、签名、
公钥和强摘要算法实际运行 `gpgv`，没有把单个归档 SHA 当成来源认证。
GNU 原始 GPL 文本及逐源码声明保留。

复现入口见 [gzip 配方](../../../src/ports/gzip/README.md)；实际使用：

```sh
python3 scripts/build_gnu_gzip.py \
  --archive build/issue133_downloads/gzip-1.14.tar.xz \
  --sdk build/issue133_sdk_v2 --profile build/issue133_profile.json \
  --output-dir build/issue133_gzip_v3 --jobs 2
python3 tests/gnu_gzip_guest.py --system-build "$XOS_BASELINE_SYSTEM_BUILD" \
  --gzip-build build/issue133_gzip_v3 --dash-receipt build/issue133_dash.json \
  --output build/issue133_guest_v2
```

`qualification.json` 是**最小化派生回执**，保留原始回执哈希、产物与源码身份、
实际状态/数值和去掉宿主位置的工具身份；不把派生字节冒充原件。
`serial.log` 与 `gpgv_status.txt` 分别为最终运行原始串口和验签状态的原字节副本。
这些叶子互不嵌入兄弟文件哈希；`manifest.json` 为唯一平铺目录清单。
派生回执把 guest 命令中的工作目录参数写成 `${XOS_GUEST_WORK}`，明确绑定
`/work`；原始串口保留实际命令。暂存的 28 个文件全部通过公开路径检查。
本目录 4 个叶子校验通过、全局报告检查列为 compliant；全局命令另外报告
17 条既有 glibc_v2/mobius 清单错误，受影响清单均与 main 基线逐字节相同，
本 PR 没有更改或将这些历史项冒称通过。

## 明确限制与失败历史

异步信号、任意 Unix 权限/所有权和文件系统时间戳恢复没有实现。未运行完整上游
`make check`；其他 GNU 工具及全部 gnulib 模块、legacy newlib 回填、二进制
打包与新 prerelease 发布均不属于本验收。本组没有改写已发布 SDK 资产。

开发期保留了中断的首个 SDK 构建、gnulib 信号类型编译失败、消费者错误包含
本快照不存在头文件的失败，以及首轮脚本误用受限 `exec-file` 导致 dash
不能创建子进程的失败。最终分别在全新输出目录重新构建或重新运行；未复用失败
状态充当通过。具体状态见派生回执与对应工作记录。
