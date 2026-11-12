# 原生开发闭环的显式输入、真实项目与双入口矩阵

2026-11-12；分支 `codex/native-dev-loop-20261112`，本提交之前的运行时修复为
`455623a1fff3be1951c040ca100ae6828dec29eb`。本组承接用户要求落实的 SL3/SL4，
不因缺客体环境而仅留下规划；测试与输入闭环已实现，完整客体结果仍如实未运行。
共享 state、路线图、债务总表和总报告由根代理整合，本记录只覆盖独立工作树证据。

## 改动

1. `shell_launch_support.py` 绑定系统全部 sources/artifacts、完整 SDK 和显式
   Make/dash 回执；接入真实 Seed 预检，并核对八个编译工具所属构建回执的 SDK。
   不再按 mtime 挑选工具，不重写 SDK 的 `archive_provenance`。
2. `shell_launch_sl3_make.py` 替换原来的小 Make 演示为真实多 TU C/archive/C++
   项目，分别走 xsh 和 dash。新 `shell_launch_sl4.py` 在同一输入、同一工作盘中
   执行项目与权限/env/cwd/FD/嵌套 Shell/真实链接失败矩阵，共 14 个顶层命令组。
3. 新 fixture 只调用公开 libc/SDK。create 降权经真实子进程准备接口进行；继承
   检查包含文件实际内容和共享偏移、exec 前后 PID 与 CLOEXEC。C++ TLS 使用跨
   翻译单元变量与修改函数，避免仅检查可被编译器常量折叠的局部值。
4. Make/dash 构建器输出准确的 receipt 路径。SL2 与诊断 SL3 也改为必传
   `--dash-receipt`，读取同一个来源检查器。SDK 生成器和工具链锁未改动。
5. 新 `test_shell_launch_bindings.py` 的 18 个用例调用实际来源/串口结果判定器；
   临时文件只充当被校验的数据，不伪造 Guest 或成功的原生构建。

完整使用方法和精确矩阵见 [native_development.md](../implementation/native_development.md)。
所有镜像导入在 Guest 前，导出在 Guest 关闭后。正例检查完整输出行和最终退出码，
负例必须真实非零，并在链接错误组看到 GNU ld 的 undefined-reference 诊断。

## 已执行的独立验证

宿主 Python 3.12.14、GCC/G++ 14.2.0，Linux x86-64；使用现有 Python unittest、
系统编译器和仓库 TU flags，没有安装新的测试框架。

| 检查 | 数量 / 结果 | 不能推导的结论 |
|---|---|---|
| 实际回执/结果判定 unittest | 18 项通过 | 不等于 GNU ELF 或 ISO 已启动 |
| 宿主 C 项目编译并运行 | 1 项目通过，输出 `SL3_C_OK` | 没有运行 XOS 内的 Make/GCC/ar |
| 宿主 C++ 项目编译并运行 | 1 项目通过，输出 `SL3_CPP_OK` | 没有验证 XOS C++ ABI/TLS/EH |
| SL4 runtime 按 COMMON_FLAGS/X86_FLAGS 编译 | 1 TU 通过，实际 newlib 头，沿用 `-w` | 不是交叉链接或 guest 执行 |
| 修改/新增 Python 语法 | 8 个文件通过 | 没有执行工具源码构建 |
| 四个 runner `--help` | 4 个通过 | 没有启动 guest |
| 四个 guest Shell 文件 `bash -n` | 4 个通过 | 不是 guest dash 执行 |
| SL3/SL4 `--preflight-only` 实际调用 | 各返回 2 / NOT_RUN | 当前系统输出目录缺失，客体执行零组 |

命令：

```sh
python3 -m unittest discover -s tests -p test_shell_launch_bindings.py -v
python3 -m py_compile scripts/build_make.py scripts/build_dash.py tests/shell_launch_support.py tests/shell_launch_sl2.py tests/shell_launch_sl3.py tests/shell_launch_sl3_make.py tests/shell_launch_sl4.py tests/test_shell_launch_bindings.py
cc tests/fixtures/shell_launch/project_c.c tests/fixtures/shell_launch/project_value.c -o build/native_dev/host/c_project
build/native_dev/host/c_project
c++ -std=c++17 tests/fixtures/shell_launch/project_cpp.cpp tests/fixtures/shell_launch/project_cpp_value.cpp -o build/native_dev/host/cpp_project
build/native_dev/host/cpp_project
bash -n tests/fixtures/shell_launch/build_project.sh
bash -n tests/fixtures/shell_launch/sl4_shell.sh
bash -n tests/fixtures/shell_launch/sl4_nested.sh
bash -n tests/fixtures/shell_launch/sl4_exec.sh
```

预检调用显式指定当前缺失的系统和输入路径，不用历史二进制补空缺：

```sh
python3 tests/shell_launch_sl4.py --system build/identity_system \
  --make-receipt build/native_inputs/make.json --dash-receipt build/native_inputs/dash.json \
  --seed-manifest build/native_inputs/seed_manifest.json --seed-root . \
  --sysroot-manifest build/native_inputs/sysroot_manifest.json --sysroot-root . \
  --preflight-only --report build/native_dev/sl4/report.json
```

SL3 使用相同参数，脚本改为 `shell_launch_sl3_make.py`，报告放入
`build/native_dev/sl3/report.json`。两者当前错误均为缺少 `build/identity_system`。
此前真实系统构建的 NASM 缺失错误仍见文件身份记录，不在这里伪报第二次系统构建。

`build/native_dev/host/validation.json` 保留以上最终检查的完整命令、退出码和日志，
`compile.json` 保留 TU 编译 flags；`sl3/report.json` / `sl4/report.json` 保留实际
NOT_RUN 与零执行数。各报告目录有平铺 `manifest.json`。这些工作产物可以重建，
本记录保留清理后仍必须知道的关键结果。

## 运行时修复与剩余验收边界

前置提交 `455623a` 已单独交接：修复 loader 在 cwd 继承时拒绝空 startup 字段，
以及 posix_spawn 混淆文件/内核错误域。其真实 libc+loader 宿主测试为 15 startup
+ 6 execvp + 10 spawn 错误域 + 1 exec cwd，共 32 组；其中新增 11 组。本提交的
18 项不能与这 32 组重复计数。文件身份、恢复等既有测试的总数也不在这里重算。

固定八进程预算未改变：xsh 是四次应用 spawn；dash 是 shell 至应用再三次应用
spawn，共四跳。xsh 缺少的 Shell 语法在报告中标为 not_applicable；普通
posix_spawn 只传递 stdio，高 FD 继承检查使用 fork+exec，未宣称扩展 startup ABI。

完整原生 14 组 guest、新回执入口的 SL2/诊断 SL3、当前工具源码构建或重链接、
全系统重建、自举均 **NOT_RUN**。下一步是提供匹配当前系统 SDK 的显式工具回执，
先通过 `--preflight-only`，再去掉此参数运行。若失败，保留脚本写出的具体命令、
串口和资源快照后修复，不放宽来源、结果标记或退出码断言以取得通过。

本记录的宿主结果只来自此独立工作树。根代理整合 upstream IPC/device/VM 等更改
后的组合验证，应由根代理另行记录，不冒充本组已经执行。
