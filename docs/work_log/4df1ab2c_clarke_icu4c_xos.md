# 4df1ab2c · ClarkE 的 ICU4C 目标依赖

2026-11-26。为 JSCOnly 构建 ICU4C 79.1 的 `data`、`i18n` 与 `uc`。Unicode
发布包 SHA-256 和签名通过，签发者为 ICU Release Robot，指纹
`E52F07877A5805F9AF4AB0ACD46C5610D06E7001`。源锁绑定发布包、签名和官方
`KEYS` 的原始 Git 字节。ICU 许可证位于原始包的 `icu/LICENSE`。

Linux arm64 宿主从空目录构建本机数据工具，再用与已验 glibc C/C++ SDK 匹配的
GCC 16.2.0 和 GNU binutils 2.47 构建 XOS 静态库。首次完整构建和来宾使用经过
签名验证的归档和同一 SDK。仓库正式入口随后从空目录完成构建与安装，宿主磁盘不足
导致复验工件导出失败。保留首轮独立的完整工件和记录。
[构建、链接和运行命令](../../src/ports/webkit/icu/README.md)

评审后从空目录重跑正式入口。宿主显式设置 `LIBS=-lxos_unavailable_host_sentinel`，
构建器清除该值，宿主与目标各自构建成功。新镜像 `8d7525f679d42e69` 运行了
逐字节相同的静态 ELF。新构建清单 SHA-256 为
`f5ccbeddf417880ea812aac4f9c9f6a7be3936b0dcda34949fb135490c4ed7b4`，客体回执为
`8928525b9d62443557ce0c72f7b12fc52a419193db22683837f6eef50f4430ae`。

QEMU 11.1.3，常规 BIOS 系统 `dcc48dddea8b7785`，xsh 输出 `ICU_SMOKE_OK` 后
退出 0。NFC 组合、德语大写、英文词边界和标准排序成功，资源前后为
`129714 / 3 / 1`。链接器报告 SDK 的 `raise` 和 `__getcwd` 缺口，本回归未使用
本地化文件装入或故障信号。

| 工件 | SHA-256 |
| --- | --- |
| `libicudata.a` | `0b5168e5c536398e4985e56bb6bf6a8a6ddabcd0886e8b81913debe6a80caf52` |
| `libicui18n.a` | `998d7813a329cc285761591110dc474d4f04321275a792cd7fbc65ee9c5af4b9` |
| `libicuuc.a` | `4522f869acd9193e5f527efca375790938aac9e803ef509df11effd9f9452c83` |
| 目标 ELF | `9d7c4f59e447524d3ba8e422c76362104c7df9dd68f2c1057abf4fc61a079d8c` |
| 镜像 | `ec8b391369f738798387d492526b1e58740bb4a9b7878189af0d375092b10494` |
| 客体回执 | `63c183669802df7561cd7674ddb5521a5c4431c6b72ce4d075c2784618c3155d` |

## JSCOnly 配置复验

在同一 WPE WebKit 2.54.2 归档上从空目录生成 XOS、x86-64、JIT 关闭的 Ninja
构建图。Linux 采样环境缺少 Ruby，于工具检查退出。macOS 宿主以 CMake 4.4.4、
Ruby 2.6.10 和 GCC 16.2.0 完成配置和生成。CMake 缓存中的 `data`、`i18n`、
`uc` 均指向经过摘要核对的目标静态库。配置日志 SHA-256 为
`937e7a3902baf009e0ce2cd876e76b1a34c1e9bac7f5c6bd8f31f7277077c7b9`。

执行真实 `cmake --build <目录> --target jsc`。首轮 bmalloc 发现目标未选分配器。
添加 `-DUSE_SYSTEM_MALLOC=ON` 重建后越过该错误。接下来 WTF 与解释器生成工具
无法编译目标线程类型。XOS 已提供基本 pthread，WTF 还需独立的线程栈、跨线程
挂起和 GC 协作路径。默认 POSIX 后端的 `sigaction` 和 `pthread_kill` 不能直接
视为可用。两个编译日志 SHA-256 分别为
`4bc0b65c9acf22bc64433036b4058a557c66c91a117ccceb8f3325d5e2338894`
和 `6e03ac7d9a1a580805469b05a26cc2b28526f095752ce278ad02277b02aceda5`。

独立安装前缀只用于开发。解释器构建、WebCore、完整 locale/文件语义、dash 入口和
发行材料各有独立验收门。
