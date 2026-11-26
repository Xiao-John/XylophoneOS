# CPython移植：当前范围与接续

2026-10-27。固定CPython3.14.9，移植线拥有src/ports/cpython/及自身构建/夹具；公共SDK、
内核ABI、文件/线程/时钟缺口由对应底座负责人整合，不在解释器内部提供假锁、假熵或假时间。

## 已交付

PY0静态解释器，PY1脚本/argv/cwd/import/文件与异常，T3-PY真实pthread/GIL，PY2基础REPL/
input/存档，以及PY3 A1–A3与B1–B4按各自输入已有专项证据；实现/哈希/限制合并至
[用户态摘要](../history/userland.md)。具体构建参数、source lock与patch以
[端口入口](../../src/ports/cpython/README.md)为准，不从“最新cache”猜产物。

## glibc 静态候选构建

`scripts/build_cpython.py` 通过显式 `--glibc-profile` 选择静态 glibc C SDK。
`--sdk` 指向同时包含 `manifest.json`、源码核验材料和 `sysroot/` 的 SDK
构建目录。使用候选 profile 时单独指定一个新输出目录。普通 newlib 参数继续
使用原有缓存和产物路径。

```sh
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build path/to/glibc-build --id xos-x86_64-glibc-static-cpython-g4-v1 \
  --output build/cpython-glibc-profile.json

python3 scripts/build_cpython.py --archive path/to/Python-3.14.9.tar.xz \
  --sdk path/to/glibc-build --glibc-profile build/cpython-glibc-profile.json \
  --output-dir build/cpython-glibc --build-python path/to/host/python3.14 \
  --compile-probe

python3 tests/cpython_glibc_guest.py --system-build build/system \
  --cpython-build build/cpython-glibc --archive path/to/Python-3.14.9.tar.xz \
  --sdk path/to/glibc-build --glibc-profile build/cpython-glibc-profile.json \
  --output build/cpython-glibc-guest
```

宿主 CPython 必须是可运行的 3.14.9，并可访问其标准库。省略
`--build-python` 时构建同版本宿主解释器。省略 `--compile-probe` 时仅配置。
输出 `py0a_report.json` 绑定源码、官方签名核验过的 glibc SDK、profile、
编译工具和实际解释器 ELF。现有普通系统镜像用 `scripts/build.py` 构建。

本候选覆盖静态解释器核心。动态扩展、Pillow、zlib、SQLite、额外压缩库、
全量标准库和交互 REPL 需要各自的资格。glibc 候选命令拒绝旧的外部扩展参数。

## 安装与运行契约

- stage/manifest逐文件记录大小/摘要，解释器在/usr/bin/python3，库在/usr/lib/python3.14，
  许可随stage安装。脚本搜索路径不得泄漏宿主/Users或.cache目录。
- 静态模块内建，不把缺少lib-dynload的提示当作完整标准库不可用，也不反向声称全部模块可用。
- 文本/argv UTF-8与文件路径范围分开；当前路径ASCII-first。REPL没有完整readline/history/
  POSIX信号语义，不假称支持KeyboardInterrupt。stdin空闲与EOF必须分别处理。
- 栈/递归与实际SDK布局对应；GC、内存失败、线程/TLS析构、文件/环境并发与退出回收按
  目标探针验收。线程SDK/profile、GIL构建模式不得从旧单线程阶段推断。
- 系统熵取真实接口，不回退固定种子/uptime；墙钟与单调时间分开，暂停VM校时边界保留。
- SDK/运行库更换先确认ABI与冻结输入；不要求完整POSIX才能交付某个独立模块。

## 后续与验收

[PY3扩展表](cpython_extensions.md)保留各模块分档；网络/TLS/在线pip、动态扩展及更完整
生态按实际需要另拆。SQLite单进程rollback journal、压缩静态流与时区数据各自资格，
不能宣布WAL/跨进程锁/所有格式完成。

下一任务先提出最小缺口和消费者探针，固定版本/库/feature/许可证，再构建隔离SDK/stage。
客体运行真实操作与负路径，绑定源码/库/解释器/stage/系统摘要并检查退出回收；import成功
不代替模块行为验收。第三方静态库许可原文/来源/对象归属与未来发行材料同时维护。
