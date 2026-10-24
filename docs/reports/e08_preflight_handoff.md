# E08 Seed/sysroot 安装清单预检交接

状态：实现并完成宿主静态用例；主端生成的 GCC/binutils bundle 只读预检通过。
本检查不构建、不复制、不挂载、不执行客体文件，也不代替 QEMU gate。

## 接口与输入合同

实现位于 `scripts/seed_preflight.py`，纯 Python 标准库。主入口：

```python
validate_bundle(
    seed_manifest, seed_root,
    sysroot_manifest, sysroot_root,
    guest_sysroot_root="/sysroot",
    required_tools=("gcc", "as", "ld", "ar", "ranlib"),
) -> PreflightResult
```

manifest 参数接受 JSON 文件路径或已解析的 mapping；两类 source 路径都只相对
调用方显式传入的对应 root 解析，不从 manifest 所在目录猜 root。Seed 采用
`install_files` 与 `tools`；工具记录须与安装清单中的 source/guest 映射一致。
sysroot 使用独立 manifest 的 `files`；每个 `guest_path` 必须原样显式包含
`guest_sysroot_root`（如 `/sysroot/include/...`），不会替清单补前缀；缺前缀时报错。
工具记录通过 source path、guest path 和预期 SHA-256 三元组关联安装项。同一 source
可以映射到多个 guest alias；工具显式选择 guest path。省略 guest path 且存在多个
source/hash 映射时报告歧义，不会任选一个。
当前 GCC bundle 可用 workspace 根作为两个显式 source root。SDK manifest 支持
`{path, sha256}` 或字符串路径加
`sdk_manifest_sha256`；若存在 `sdk_input_hashes`，还会读取 SDK manifest 所在目录下
的实际文件逐项核对，不要求其 build ID 与当前 SDK metadata 相同。

结果 `PreflightResult` 可用 `to_dict()` 序列化，字段为 `ok`、`not_guest_test`、
`seed_files`、`sysroot_files`、`tools`、`summary` 与完整 `diagnostics`。CLI 要求显式
传 `--seed-manifest/--seed-root/--sysroot-manifest/--sysroot-root`，JSON 写 stdout，
发现任意错误时 exit 1；`--report` 只写入调用者明确提供的位置。

## 检查范围

- source 路径拒绝 POSIX/Windows host 绝对路径、反斜线、`.`/`..`、空段与控制字符；
  首段为 `localpilot` 的 source 无条件拒绝，不读取该隔离项目。
  source 中间任一文件组件为 symlink 时拒绝。guest 路径必须是 canonical ASCII
  绝对文件路径，允许空格，最多 255 UTF-8 字节；拒绝 dot 路径、尾斜线、重复斜线、
  FAT 不兼容字符及大小写折叠冲突。
- 对 Seed 与 sysroot 所有安装项实际读取并核对 SHA-256；同时核对可选 `bytes`。
  跨两类清单检查目标路径重复、大小写冲突、文件与目录前缀冲突。工具名受白名单
  限制，必需工具逐项检查；工具必须是安装清单成员且映射一致。
- 工具必须是 ELF64 little-endian AMD64 ET_EXEC，拒绝 INTERP/DYNAMIC、未知 PHDR、
  可执行 GNU_STACK；核查 PHDR/文件范围、LOAD 对齐与重叠、R/W/X 权限、入口落在
  可执行文件字节、TLS/heap/stack 保留区、TLS local-exec 子集和映射页预算。空 PT_TLS
  与 XOS loader 一样忽略。image end/guard 按实际 ABI 为 `0x7ffdb000`。该检查只
  分析元数据，不执行工具。
- sysroot 必须显式给出 root 与 manifest。host C++ runtime 与 target sysroot 有不同
  role；metadata 中 `host_stdcxx.path` 下的文件一旦被列入 target sysroot 即报错，
  不会从 host 路径自动寻找/安装 libstdc++。

诊断按项累积，不在首个错误停止。`summary.not_guest_test=true` 永远保留，静态
预检通过不表示实际客体命令、资源峰值或 syscall 已验收。路径含空格可通过清单
格式验证；当前 supervisor 命令输入是否能表达此路径需由对应功能 gate另测。

## 验证证据

宿主命令：

```sh
python3 -m unittest tests/seed_preflight_cases.py
python3 -m py_compile scripts/seed_preflight.py tests/seed_preflight_cases.py
```

结果：18 个确定性正负用例通过；py_compile 通过。fixture 在 tempfile 中生成微型
ELF64，不调用 host compiler、QEMU 或构建系统。覆盖路径安全、symlink、FAT 冲突、
重复/前缀冲突、哈希/尺寸、tool 白名单与映射、ELF/TLS/资源约束、host C++ runtime
隔离、SDK manifest/input hash。

主端集成 bundle 的只读 API 调用（source roots 显式传 workspace root）结果：
171 个 Seed install 项、151 个 target sysroot 项、10 个 tool、累计 105,373,595
字节、0 diagnostics；required `gcc/cc1/as/ld/ar/ranlib` 均通过静态 ELF 检查。没有
将结果写入 `build/`；该观察不是 GCC/C 客体运行验收。

## 文件占用

本任务新增 `scripts/seed_preflight.py`、`tests/seed_preflight_cases.py`、本交接页。
未修改 GCC/C++ smoke harness、Seed、SDK、`build/`、其他脚本或 `localpilot/`。
