# E08-6 集成 gate 交接

状态：harness 与 C/C++ 小型多 TU fixture 已新增；仅完成 AST/文本静态检查。
本次没有执行脚本、预检 API、构建、临时盘或 QEMU。E08-6 当前证据为 `not_run`。

## 输入与阶段入口

文件：`tests/e08_integration_smoke.py`、`tests/fixtures/e08_integration/c/`、
`tests/fixtures/e08_integration/cpp/`。测试使用 E08-4/5 已有的
`seed_preflight.validate_bundle`、`gcc_seed_smoke.import_manifest_files`、
`make_work_disk.create_fat32`、`work_disk.transfer`、`process_smoke.command/resources`
和 `boot_smoke.Guest`。不修改旧 smoke/soak。

默认只预检并打印 `guest_execution=not_run` 的 JSON；只有显式 `--run-guest` 才建立
临时 FAT32 镜像、安装清单文件并启动指定 XOS image。Guest run 强制给 `--report`，
失败会把完整 report 保留到该路径。Seed、sysroot manifest/root 逐语言显式传入：

```sh
python3 tests/e08_integration_smoke.py --language c \
  --c-seed-manifest build/gcc_bundle/seed_manifest.json --c-seed-root . \
  --c-sysroot-manifest build/gcc_bundle/sysroot_manifest.json --c-sysroot-root .
```

主端执行 C 运行 gate 时，在命令末尾加 `--run-guest --report build/e08_6_c_report.json`。
这会生成**部分语言**证据；报告为 `passed_partial_language`，不表示 E08-5 或 E08 整体
通过。G++/C++ manifest 到货后可独立使用 `--language cpp` 和对应 `--cpp-*` 参数。
同时验收两种语言时用 `--language all` 并提供两组 manifest/root；两种语言安装项
若映射同一 guest path，只有相同 SHA 才合并；冲突直接失败。

## Guest run 流程

每个所选语言在同一个临时工作盘上导入真实 Seed/sysroot 和最小三 TU 项目。C 项目由
GCC 编译并将一个 TU 放入静态 archive，GCC driver 链接 archive 与其他 TU；C++ 项目
使用 `std::string`/`std::to_string`，以真实 G++ 链接其静态 archive。首次运行检查
`E08_INTEGRATION_{C,CPP}_V1_42` 与退出码 0。随后通过 supervisor `edit` 进入真实
editor，以 `:c` 清空并逐行输入 main 源码，`:wq` 保存；重新编译和链接后必须输出
对应 V2 标记及退出码 0。

所有命令记录实际输出、诊断、退出码和资源计数，并要求任务/页/完成记录回到启动
基线。随后执行 `sync`、关闭 QEMU、对同一临时盘重启，执行 V2 产物并检查相同结果。
最后仅在 QEMU 关闭后离线导出 edited 源码、静态库、产物和清单中实际调用的 Seed
tool 文件；源码必须逐字节等于 editor 保存结果，Seed tools 导出 SHA 必须与 manifest
输入 hash 相同。Report 绑定 XOS image/system manifest、每组 Seed/sysroot manifest
与 SDK hash、preflight 全部源文件 hash、产物和串口/QEMU 运行记录。

普通 E08-4/5 工具设施矩阵、并发设施测试、压力/soak 不重复。E08-6 不自动声明
`e08_complete`；单语言报告是 partial。目标 guest 尚未在本任务运行。

## 静态检查

本组只做了 Python `ast.parse` 和 fixture 文本限制检查：harness AST 可解析；8 个
fixture 均无 NUL、低于 editor 8 KiB 缓冲，且每行短于 supervisor editor 输入边界。
这些检查不证明 XOS 编译器命令、editor 序列、QEMU 重启或 FAT 导入实际通过。
