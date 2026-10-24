# E08 C++ ABI 探针准备交接

状态：**源码与 runner 已准备；目标 C++ runtime 尚未交付，客体 ABI 探针未运行**。
本页只记录 C++ ABI 探针准备，不代表 E08-5 通过。主端负责构建、装盘、XOS 客体执行和最终判定。

## 修改范围

新增 Apache-2.0 自研文件：

- `tests/fixtures/cpp_abi/`：按功能分开的 C++ 探针源码。
- `scripts/build_cpp_abi_probe.py`：显式 runtime manifest 预检与目标 ELF 构建器。
- `tests/cpp_abi_smoke.py`：默认只生成构建/待运行报告；显式传 `--run-guest` 时，在临时 FAT32 盘导入并由当前 XOS 客体执行，不在宿主运行 ELF。
- `docs/reports/e08_cpp_abi_handoff.md`：本交接页。

探针范围为 `string_vector`、`exceptions`、`rtti`、`local_static`、`tls_destructors`、`multi_tu`。已有 trivial TLS/CRT 压力不在这里重复。异常、RTTI、标准容器与非平凡 TLS 都必须由真实目标库支持；没有 runtime 时不会制造替身头文件或库。

## Manifest 接口

runner 接受四个必需参数；默认只构建并记录 `built_not_run`。只有明确传 `--run-guest` 才启动客体验证：

```text
python3 tests/cpp_abi_smoke.py \
  --sdk <immutable-sdk-root> \
  --runtime-prefix <actual-target-cxx-runtime-prefix> \
  --runtime-manifest <manifest.json> \
  --output-root <explicit-output-directory> \
  --features local_static,multi_tu \
  --run-guest
```

manifest 为 JSON，当前 schema_version 为 1。路径必须明确绑定到 `sdk` 或 `runtime` 根；不会猜测系统 include 搜索目录。核心字段：

```json
{
  "schema_version": 1,
  "status": "prepared",
  "target_triple": "x86_64-elf",
  "runtime_kind": "target_application_runtime",
  "sdk_manifest": {"path": "manifest.json", "sha256": "..."},
  "compiler": {"path": "/absolute/path/to/x86_64-elf-g++", "sha256": "...", "target": "x86_64-elf"},
  "host_library_build_flags": [],
  "include_dirs": [{"root": "runtime", "path": "include/c++/VERSION", "sha256": "..."}],
  "crt": {"root": "sdk", "path": "usr/lib/crt0_posix.o", "sha256": "..."},
  "linker_script": {"root": "sdk", "path": "usr/lib/user.ld", "sha256": "..."},
  "archives": [{"root": "runtime", "path": "lib/libstdc++.a", "sha256": "...", "role": "libstdc++"}],
  "compile_flags": [],
  "link_flags": [],
  "feature_flags": {"exceptions": [], "rtti": []},
  "features": {
    "local_static": {"status": "ready", "evidence": "build configuration reference"},
    "exceptions": {"status": "not_ready", "evidence": "..."}
  }
}
```

实际 manifest 应提供每个被引用文件的 SHA256。include directory 的 SHA256 按相对路径排序，将每个普通文件的相对路径、NUL 字节和文件 SHA256 原始字节依次输入 SHA256；目录不得含 symlink。`compiler.path` 是真实交叉编译器，manifest 必须记录它的哈希及 target。libgcc 来源、版本/构建标识和实际库哈希应放入 manifest 的 `archives` 记录或附加 `provenance` 字段，供复核实际展开器来源。

`features.*.status = ready` 是运行库/构建配置声明，含义仅为“允许尝试编译链接”。它不表示客体执行通过。当前若库使用 `-fno-exceptions`，`exceptions` 模式会被阻断；若使用 `-fno-rtti`，`rtti` 会被阻断。未选择的 feature 不会阻塞单项验证，例如 `--features local_static` 不因 exceptions 未就绪而拒绝。纯 host 工具闭包必须声明非 `target_application_runtime`，会得到 `not_ready`。

状态约定：缺运行库或声明未就绪返回 exit 2，报告 `not_ready`，且不打印 PASS；编译/链接命令非零返回 exit 1、报告 `failed`，保留真实命令和输出；目标 ELF 构建成功但尚未在 XOS 执行，报告 `built_not_run`。guest 模式核验当前 XOS build manifest 与镜像哈希，只运行 ELF 哈希复核通过的 `built_not_run` 产物；客体退出码、feature marker 或资源回收任一失败都记 `failed`。只有客体实际执行并核对预期输出后，才能把某 feature 记作 `passed`。这仍是早期 ABI 探针，不是 E08-5 原生编译 gate。

## 探针行为与证据边界

每个 feature 独立编译和链接，产物进入显式 `--output-root` 的对应子目录。报告绑定 manifest、SDK manifest、交叉编译器、探针源文件、CRT、链接脚本和库的哈希，并保存每条真实 compile/link 命令及 stdout/stderr。builder 不删除或覆盖输入，不写共享 `build/`。guest 模式只接受 builder 报告中 `built_not_run` 且 ELF 哈希复核通过的产物；它校验当前 `build/xos.img` 与 `build/manifest.json` 一致，创建临时 FAT32 盘、导入 `/bin/`，逐个 `exec-file` 并检查客体输出、退出码和任务/页/完成记录资源回到基线。只有该客体执行路径会把 feature 标为 `passed`。`multi_tu` 要求 A 构造早于 B，正常退出时 B 的析构检查早于 A；TLS 析构 marker 必须出现在正常退出 marker 后，且输出不能包含 `=fail`。

- `string_vector`：实际 `std::string` 与 `std::vector<int>` 操作。
- `exceptions`：跨两个 noinline 帧 throw/catch，并检查展开时局部对象析构。
- `rtti`：多态 `dynamic_cast` 与 `typeid`。
- `local_static`：函数内静态对象重复访问只构造一次。
- `tls_destructors`：非平凡 `thread_local` 初始化，并要求正常 main return 时析构标记；异常/强制终止路径不在该探针声称范围内。
- `multi_tu`：两个 translation unit 的全局初始化依赖及逆序析构关系。

这些 fixture 只覆盖明确列出的 ABI 行为，不等于完整 C++ 标准库兼容性、并发线程 TLS 或完整 POSIX。新自研代码 Apache-2.0；GCC runtime、libstdc++、libsupc++、libgcc 和其他上游组件继续保留各自许可证与 runtime exception，实际来源和例外材料由 runtime 交付者提供，不能以本页替代组件审计。

## 当前检查与下一步

本轮只做源文件与 Python AST 静态检查；未调用交叉编译器、未构建目标 ELF、未运行 QEMU/客体。C++ runtime 未交付，因此当前状态是 `not_ready`，不是 ABI 失败，也不是通过。

主端收到真实目标运行库和哈希绑定 manifest 后，可先选择已声明可尝试的单项 feature 构建；默认只准备。需要真实验收时再显式传 `--run-guest`，测试会复核 ELF 哈希和当前系统镜像绑定，之后在 XOS 中按 feature 分别执行并记录串口输出、退出码及资源回收。仅客体结果可把该 feature 从 `built_not_run` 推进到 `passed` 或 `failed`。
