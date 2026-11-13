# 原生开发闭环：SL3 C/C++ Make 与 SL4 双 Shell 矩阵

SL3/SL4 使用显式回执选择系统、SDK、Make、dash、GCC/G++、binutils 和应用
sysroot。`tests/shell_launch_sl3_make.py` 执行真实多文件项目；
`tests/shell_launch_sl4.py` 包含同一项目并增加权限、环境、cwd、FD 与嵌套 Shell
矩阵。测试代码已实现；2026-11-12 本组没有可运行的当前系统镜像/SDK，完整客体
执行为 **NOT_RUN**，不能把宿主测试或预检当成原生编译通过。

## 输入与构建来源

先按当前工具链锁和构建脚本的宿主要求构建系统及工具。Make/dash 构建器在输出
JSON 中提供准确的 `receipt` 路径，不再让测试按缓存修改时间挑选二进制：

```sh
python3 scripts/build.py --output-dir build/native_system
python3 scripts/build_make.py --sdk build/native_system/sdk
python3 scripts/build_dash.py --sdk build/native_system/sdk
```

编译器和 binutils 使用仓库已有 `build_gcc.py` / `build_binutils.py` 流程，明确
传入同一 SDK 及预期 manifest 哈希。完整 G++ 源码重建不是本组新增能力；已有
交付对象可通过 `relink_gcc_seed.py --gxx` 对明确的新 SDK 重链接，这必须仍记为
重链接，不能称为源码重建或编译器自举。宿主编译器本身所需的 C++ 运行库，与
安装到客体应用 sysroot 的运行库是两种输入，按各脚本的显式参数分别提供。

使用现有准备器生成安装清单，三个 C++ 参数须同时提供：

```sh
python3 scripts/prepare_gcc_seed.py \
  --gcc-manifest "$gcc_receipt" --binutils-manifest "$binutils_receipt" \
  --gxx-manifest "$gxx_receipt" --runtime-manifest "$runtime_receipt" \
  --runtime-prefix "$runtime_prefix" --target-sdk build/native_system/sdk \
  --output-root build/native_bundle
```

这里的 shell 变量由操作者设为实际构建输出回执/目录，不由脚本猜测。测试会验证：

- 系统 manifest 中全部源码与产物哈希，以及 SDK 完整文件清单和 build ID。
- Make/dash 回执的 profile、完整 SDK 输入、源码输入与所选 ELF 的哈希。
- Seed/sysroot 的实际安装文件、工具映射和既有预检规则。
- gcc、cc1、g++、cc1plus、as、ld、ar、ranlib 均由 Seed 绑定的构建回执覆盖，
  且这些工具的运行时 SDK 与当前系统 SDK 相同。仅替换应用 SDK 的旧 Seed 会拒绝。
- 安装到 `/sysroot` 的头、CRT、链接脚本与 SDK 库，确实等于选定 SDK 的字节。

这些操作只读取 SDK，保留其 `archive_provenance`；不重写 manifest 来让旧产物
看似属于新构建。缺失输入返回 `NOT_RUN`/退出码 2，存在但不一致的输入返回失败。

## 执行命令

把 Make/dash 构建器打印的路径保存为 `make_receipt`、`dash_receipt`。从仓库根运行：

```sh
python3 tests/shell_launch_sl4.py \
  --system build/native_system \
  --make-receipt "$make_receipt" --dash-receipt "$dash_receipt" \
  --seed-manifest build/native_bundle/seed_manifest.json --seed-root . \
  --sysroot-manifest build/native_bundle/sysroot_manifest.json --sysroot-root . \
  --preflight-only
```

预检成功只产生 `preflight_passed`，`guest_execution` 仍为 `not_run`。去掉
`--preflight-only` 才启动客体。把脚本名改为 `shell_launch_sl3_make.py` 可单独
运行项目的四组命令。两者均支持 `--report`；默认目录分别为
`build/shell_launch_sl4/` 与 `build/shell_launch_sl3_make/`。

已有 SL2 和诊断 SL3 入口也要求显式 dash：

```sh
python3 tests/shell_launch_sl2.py --system build/native_system --dash-receipt "$dash_receipt"
python3 tests/shell_launch_sl3.py --system build/native_system --dash-receipt "$dash_receipt"
```

所有工作盘创建和导入在 Guest 构造前完成，QEMU 关闭后才导出项目产物。测试不向
已被客体挂载的镜像同时写入。SL4 探针使用选定 SDK 和当前锁定交叉编译器构建；
缺交叉编译器也记录未运行，不以宿主可执行程序代替客体探针。

## 真实项目与验收矩阵

`tests/fixtures/shell_launch/project.mk` 沿用当前 sbase Make 的显式 `-B` profile。
C 项目包含两个翻译单元，调用真实 `ar` 生成静态 archive 后链接；C++ 项目包含
两个翻译单元，使用 string/vector、虚函数/RTTI、跨单元异常与析构、跨单元可变 TLS。
项目没有以预生成 ELF 代替客体编译结果。

| 命令组 | 入口 | 实际断言 |
|---|---|---|
| 1 | xsh | 普通 `make -B` 构建 C/C++ 项目并正常退出 |
| 2 | xsh | 新生成的 C ELF 返回零并打印完整 `SL3_C_OK` 行 |
| 3 | xsh | 新生成的 C++ ELF 返回零并打印完整 `SL3_CPP_OK` 行 |
| 4 | dash | 脚本调用普通 make 重建并运行两个项目，三个完整结果行均出现 |
| 5–6 | xsh | 普通程序与字节相同的改名程序均继承 create 权限 |
| 7 | xsh | 连续四次应用 spawn，每层查询到继承权限，最终逐层回收 |
| 8 | xsh | 父显式降权；子 raw create/spawn/fork 被拒；改名 exec 后仍无权 |
| 9 | xsh | env/cwd/stdio、相对 addopen、共享偏移、fork+exec 别名 FD/CLOEXEC/PID |
| 10 | xsh | 受限 `exec-file` 入口保持无 create 权限，替换镜像也不提升 |
| 11 | dash | 上述权限与继承，再加空参数、空格、管道重定向、嵌套脚本和子 Shell |
| 12 | dash | 显式 exec 保持原 Shell PID |
| 13–14 | xsh / dash | 有效 C 源文件的未定义符号触发真实 GNU ld 错误，非零退出且有诊断 |

每个顶层命令都核对前后的进程/completion/pages 资源快照。结果标记必须完整占一行，
支持 LF/CRLF；输入回显中包含标记不能通过。以最后一个退出记录为准，负例的零退出
不能通过。完成后记录三个客体产物的哈希/长度和完整串口日志。

固定八个进程槽不扩容。xsh 链为应用的四次 spawn；dash 链为
`dash → probe → probe → probe → probe` 四跳，其中应用 spawn 三次，留出常驻
supervisor/files/audio 的槽位。两者的准确链路写入报告，不把较短链冒称五个应用。

xsh 本身没有 cd/export、引号语法、管道、子 Shell 或替换自身的 exec，这些 Shell
语法只在 dash 入口验收；xsh 启动的应用仍验收实际 libc 继承。startup-v2 的普通
posix_spawn 只传递 stdio；高 FD 和 CLOEXEC 用 fork+exec 验证，不宣称任意 FD 的
posix_spawn 继承已实现。

## 独立宿主验证与未运行项

```sh
python3 -m unittest discover -s tests -p test_shell_launch_bindings.py -v
python3 -m py_compile tests/shell_launch_support.py tests/shell_launch_sl3_make.py tests/shell_launch_sl4.py
c++ -std=c++17 tests/fixtures/shell_launch/project_cpp.cpp tests/fixtures/shell_launch/project_cpp_value.cpp -o build/native_dev/host/cpp_project
```

2026-11-12：18 项真实回执/输出判定单测通过；C/C++ fixture 在宿主编译执行通过；
SL4 runtime 以仓库目标 TU flags 配合实际 newlib 头完成宿主编译；Python 和四个
Shell 脚本语法检查通过。这些不构成 XOS 内的 GCC、Make、TLS 或 C++ ABI 验收。
SL3/SL4 实际预检因 `build/identity_system` 不存在返回 2，客体命令执行数为零。
此前系统构建尝试因 NASM 缺失而停止；当前工具回执也没有在本环境重建。

原生完整 guest 的 14 组、SL2/诊断 SL3 的新回执入口、当前 GNU 工具源码构建/重链接
和系统自举均 **NOT_RUN**。完整命令和本组独立证据见
[本组记录](../work_log/c274a9e1_native_development_gates.md)。主线整合后的组合验证
由合并者另行登记，不合并进这组独立结果。
