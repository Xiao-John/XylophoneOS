# 65b70444 · CPython 使用 XOS newlib 的可执行文件检查

基于[线程版 newlib 回退验收](a111ac3e_cpython_newlib_getpath.md)，
复用 PR #147 的 `xos-threading-v1-experimental` SDK 和原 CPython
3.14.9 构建入口。裸命令 `python3` 由 xsh 成功启动时，解释器内部原先找
不到 `sys.executable`。FAT 常规文件没有 POSIX 文件执行位 `0111`，
XOS newlib 的 `access(X_OK)` 则调用原生 ELF 检查。

只调整 CPython 的 XOS newlib `getpath_isxfile`。真实 `stat` 先确认普通
文件，再由现有 `access(X_OK)` 判断映像。目录可以有搜索权限，仍须跳过。
文件不可用时继续按上游规则搜索下一个 PATH 候选。分别比较 XOS glibc、
Windows 和其他目标时，补丁前后的预处理结果一致。文件服务、SDK 和 ABI
沿用原合同。

## 构建与测试

原 `build_cpython.py --sdk ... --compile-probe` 生成静态解释器，目标
`getpath.o` 确实引用 `stat` 和 `access`。新增 PY1 的真实裸命令验证，
同一文件的显式路径启动仍由原 PY1 探针独立验证。

另外用同一 SDK 编译普通 `posix_spawn` 进程测试。它使用显式可执行文件
和裸 `argv[0]`，给子解释器传入固定 PATH，分别测试无效候选之后有真
ELF 的情况和全部候选不可用的情况。其中目录可搜索、普通文本报 `EACCES`、
缺失文件报 `ENOENT`，普通文件带尾斜杠报 `ENOTDIR`。在同一正常系统
和同一私有 FAT32 磁盘布局下对比修复前后的解释器。

PY1 八项、T3-PY 五项全过。QEMU 对照中，旧解释器遇到真正 ELF 时 `sys.executable`
仍为空，子进程按预期断言失败。新解释器在跳过目录、普通文本、缺失文件和
无法遍历的路径后找到 `/usr/bin/python3`。PATH 只有这些候选时返回空，
`sys.prefix` 和 `sys.exec_prefix` 仍指向 `/usr`。两组探针均恢复到
129698 空闲页、3 个任务和 1 个完成记录。首次编译时 VM 可用内存不足，
`cc1` 被终止。保留失败回执，释放本次构建的旧中间产物后，用相同源码和
SDK 从原入口重建通过。

| 输入与回执 | SHA-256 |
| --- | --- |
| 固定线程版 newlib SDK manifest | `88b1209055f1c2c6a24929d58af04bee7305d0b31c58ccdc3db20e2032f56a93` |
| 修复后旧入口编译回执 | `42fe9b0f998aa4e4cc118733a20c47ad21425e50b3e4ad9405221f8985f7618a` |
| 正常系统 `7dc11cb03f40d912` ISO | `c971a65f89c622b86ea885ef98fae6243be757f704697dc697e66966e9284dd4` |
| 系统 manifest | `65128e4cdd63ee777d1ba662162404083d581d67dc5251848115fe8382c6b679` |
| staging manifest | `16f0cc847311355e73e124145eb8e5be5fa5ebfc21f6779000adfc39fadde145` |
| 客体解释器 ELF | `59b20d15a717f4af3bd60650ad3a76435d1d12e4e7a1a74d96541d05c05b6e3c` |
| 原生 PATH 子进程探针 ELF | `66865cd828d88110a906383e005ca73c8a1bd98f202325efa28178ba07b17232` |
| PY1 回执 | `a060ff8178742b7ee280b8dcb46d525f26e9afffc20a1656aadd92a3479e0dca` |
| T3-PY 回执 | `681583f22b0481e5685fcd58c221708c18757bdcd82bda5b47bfc3f627782c72` |
| 旧解释器 PATH 对照回执 | `b69f1ff77e943b868407cdf96ef981e956be7c36aa2be7a20c6e0832184b8ced` |
| 新解释器 PATH 正负路径回执 | `e356b9fd7a3ac5ef774b877b74ceb4caa4a27a947233973006c6340d72c16a4b` |
