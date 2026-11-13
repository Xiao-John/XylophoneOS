<!-- coderabbit-ai-generated:v1 -->

# /dev 虚拟路径审查修复

2026-11-13，基线 `0bc1dcf48b0c44deb79241cc5ad78e2707426a4b`。

四项反馈均在当前代码复现并修复。文件服务按路径分量识别根目录的 dev，支持
`stat("/dev/")`、`/./dev/null`、`/dev/./null`，保留中间目录实际存在性检查。
`replace_begin` 在打开临时文件前拒绝虚拟对象，防止 parent/leaf 重建指向根目录 null。
保留 65534、65535 两个稳定身份，FAT 分配器不再使用这两个编号；不改 ABI 布局。
这是对原来“其余编号单调分配”的明确例外，FAT 可分配身份容量减少两个。
null 写入在更新偏移前检查现有 seek 支持的 `0xfffffffe` 上限，失败返回 no_space 且不移动偏移。

修改 `src/user/services/files.cpp`、文件语义 fixture 与身份契约。
新增回归覆盖虚拟目录尾斜杠、点分量、缺失中间目录、stat/open/fstat 身份一致、
槽释放后身份稳定、FAT 身份耗尽边界、存在实体 dev/null 时 staging 拒绝与偏移越界。

验证：Python 3.14.4、G++ 15.2.0；`python3 tests/file_semantics.py` 通过 26 项；
`python3 tests/file_identity_host.py` 通过文件语义 26 项、身份 24 项、libc/SDK 9 项。
首次边界测试误将 u32 最大值当作 seek 上限，失败后将写入及测试对齐原有范围，复验通过。
报告位于 `build/file_semantics/report.json`、`build/file_identity/report.json`。
未运行客体构建/QEMU；以上为生产服务和真实 FatFs 的宿主测试，不声明客体验收。
未扩展 readdir("/dev")。后续可在准备完整工具链后执行客体 dev_null 检查。
