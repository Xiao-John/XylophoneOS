# E08-4/5 功能 gate cases 交接

状态：**harness 与 fixtures 已编写；未运行，等待 Seed 和 target sysroot manifest/客体输入**。
范围仅 `tests/gcc_seed_smoke.py`、`tests/cpp_seed_smoke.py`、
`tests/fixtures/gcc/`、`tests/fixtures/cpp/` 与本页。没有改旧压力测试，没有构建、启动
QEMU 或写 `build/`。

## 调用合同

两套 harness 都要求显式给出 manifest 与其对应宿主根目录：

```text
python3 tests/gcc_seed_smoke.py --seed-manifest <gcc-manifest.json> \
  --seed-root <host-install-root> --sysroot-manifest <target-sysroot.json> \
  --sysroot-root <host-sysroot-root>
python3 tests/cpp_seed_smoke.py --seed-manifest <gxx-manifest.json> \
  --seed-root <host-install-root> --sysroot-manifest <target-sysroot.json> \
  --sysroot-root <host-sysroot-root>
```

Seed manifest 使用顶层 `sdk_manifest`、`sdk_manifest_sha256`、`tools`、`install_files`。
`install_files` 白名单的每项绑定 install-root 相对 `path`、`guest_path`、`sha256`；导入时严格按
`guest_path` 放置，保留 GCC libexec 层级。`tools` 每项绑定宿主相对 `path` 和 `sha256`，可带
`guest_path`，否则按同路径 install 白名单解析。target sysroot manifest 使用 `files` 白名单，字段
同样为 `path`、`guest_path`、`sha256`，guest 路径必须位于 `/sysroot/` 下。sysroot 没有宿主默认值，
测试不从宿主系统目录补文件。

GCC/G++ 可执行路径默认取 `tools.gcc.guest_path` / `tools.g++.guest_path`，没有该字段时按 install
白名单查找。`--guest-gcc` / `--guest-gxx` 可显式覆盖。归档工具同样从 manifest 解析。2 GiB 临时
FAT32 盘只导入两份 manifest 的白名单文件和本组 fixtures；符号链接、白名单外文件、哈希不符或
重复 guest 路径都会失败。报告默认写入对应 `build/*_seed_smoke_report.json`，由主 agent 串行运行
后生成。

## 覆盖范围

C fixtures 覆盖头文件、多翻译单元、对象 `-c/-o`、静态 archive、libgcc 的 128 位除法/取模辅助例程，
以及语法、链接符号和缺头文件错误。harness 通过 `-v` 检查真实 cc1/as/ld 调用；客体生成的 libgcc 对象由宿主 nm 只读检查，必须
引用 `__udivti3` 与 `__umodti3`，再由客体静态链接并运行。其他链路也在客体执行，逐命令检查退出
状态、诊断及物理页/任务/completion 资源恢复；输入源码在同步后离线逐字节比较。

C++ fixtures 覆盖 `vector`/`string`、跨 TU 全局初始化/析构标记、静态库、异常展开时析构局部对象、
RTTI、TLS 初始化。TLS worker 为两个独立客体任务分别设置不同的 TLS 值，以共享 ready 文件形成
并存屏障，在等待共享就绪屏障后分别跨越 PIT tick 并经 syscall yield 交错读取，最后检查各自 TLS 值仍隔离并回收任务资源。这测试 XOS
任务调度下的 TLS 生命周期，不代表 `std::thread` 或线程并发验收。

## 验证状态与下一步

- 编写完成：C/C++ 功能源、错误源和两个功能 gate harness。
- 未运行：Seed 构建、C/C++ 客体功能 gate、QEMU、峰值内存实测和产物 ELF 检查。
- 可做的静态语法检查不编译 target fixtures，也不写 `build/`；target 源码必须由客体 GCC/G++ 编译。
- 主 agent 冻结并交付 manifest 文件名及 `tools` 路径后，由主 agent 在统一构建/QEMU窗口实际运行并
  写入报告。若最终字段与本合同有差异，先按协调页更新读取映射，再运行。

所有新增自研源码带 Apache-2.0 SPDX。GNU Seed/sysroot 的第三方许可状态由工具链/主 agent 交接，
功能 gate 不宣称完成分发许可审计。
