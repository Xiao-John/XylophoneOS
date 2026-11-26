# a111ac3e · CPython 3.14.9 的线程版 newlib 回退

在 `49e5d74b` 上用原 CPython 构建入口复用 PR #147 的
`xos-threading-v1-experimental` newlib SDK，并按原 manifest 核对 2556
个文件。旧配置启用 `HAVE_REALPATH`，没有 `HAVE_READLINK` 或
`HAVE_LSTAT`。原入口在 `Modules/getpath.c:496` 以 `lstat` 未声明退出。
用目标编译器单独核对 SDK 头文件，`stat` 调用可编译，`lstat` 调用被拒绝。
SDK 静态库定义 `stat`、`_stat` 和 `realpath`。

XOS newlib 的路径命名空间没有符号链接。补丁让该配置下的 CPython
启动定位使用 `stat`，复用现有 CPython POSIX 模块对无符号链接路径的处理方式。
原生 `stat` 经文件服务取得路径类型及元数据，并传回真实错误。
只修改解释器自身的路径检查，SDK 及公开 ABI 沿用原合同。
同一上游函数的预处理比较确认 glibc 和其他目标保留原路径。

```sh
python3 scripts/build_cpython.py --archive "$cpython_archive" \
  --sdk "$threaded_newlib_sdk" --build-python "$host_python" --compile-probe
python3 scripts/build.py
python3 tests/cpython_py1_smoke.py --work "$cpython_work"
python3 tests/cpython_t3_py_smoke.py --work "$cpython_work"
```

修复后旧入口重建成功，实际 `getpath.o` 引用 `stat`，且无 `lstat` 引用。
静态 x86-64 ELF 带 `PT_TLS`。本轮沿用项目锁定的 CPython 3.14.9
源码与相同版本的宿主 Python，构建最多使用两个作业。

## 客体验收

从 `0489b6f1` 重建正常系统 `ab1460552e5ffa7b`。QEMU 11.1.3
在私有 FAT32 盘上安装旧 staging 入口生成的 560 个文件。
PY1 通过 7 项，包括用 `/usr/bin/python3` 启动、确定 `/usr` 下的
`sys.prefix`、`sys.exec_prefix` 和标准库路径、区分普通文件和目录，以及
核对缺失文件的 `ENOENT` 与普通文件带尾斜杠的 `ENOTDIR`。
原有裸命令、脚本参数和导入、二进制读取与异常退出检查也通过。
T3-PY 通过 5 项，覆盖锁与条件变量、文件 I/O 时后台线程进度、异常钩子、
daemon 与非 daemon 退出。每项结束后均回到 129698 空闲页、3 个任务和
1 个完成记录。

首次将启动路径探针用于裸命令 `python3` 时，xsh 已运行正确的 ELF，
而解释器内部的 `sys.executable` 为空。FAT 常规文件报告 `0644` 或
`0444`，上游 CPython 的内部 PATH 检查依赖 POSIX `0111` 位。
本轮将新的启动路径探针固定到显式路径，保留原有裸命令脚本验证。
启动时仍有关于静态 staging 缺少 `lib-dynload` 的既有提示。
本轮的范围是固定线程版 SDK 和静态标准库子集。将同一个构建入口指向本次
正常系统生成的无线程 SDK 作为对照，仍明确报 `Require native threads`。

| 输入与回执 | SHA-256 |
| --- | --- |
| CPython 源包 | `e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53` |
| 冻结线程版 newlib SDK 归档 | `6de0009f7c264ce6b4b500965b0007377f1c31a5fca78a7b2fdcebc6740ba709` |
| SDK manifest | `88b1209055f1c2c6a24929d58af04bee7305d0b31c58ccdc3db20e2032f56a93` |
| 同版本宿主 Python ELF | `3f5f805d394a707896ca7972483d803a2119dd4955357ad856d45ccee4cc694e` |
| 旧入口编译失败回执 | `c48c351dc4acc92209c31e0e9bb9ad1700f12838a36b6a3f93a7eefadba36f62` |
| 修复后编译回执 | `d733fd9d39e1a7bb2aba5526a3b237b925c5a39b2207880f71b7dcfaa68b9683` |
| 带调试信息的解释器 ELF | `580c4fb5a290c8024df82fd53978cfa49bef68d00f679c2922c4055a9bb64518` |
| 正常系统 manifest | `65d74e081321115bf7b01f7680ae9e3786fdbd320717b7459e4cf8cda7a19214` |
| 正常系统 ISO | `1eb80ade4541eee45b825b58b19f7d08d78f34b15550a47814df48da68a2a854` |
| staging manifest | `8327b782cf4ad290a21acd8a1eee62fab357e35e7c51d0264b6dd1c7d7279bbe` |
| 客体解释器 ELF | `cc9258b0f61893e67b04e160937380bbac129d1562d23b1a061f32344ece894f` |
| PY1 回执 | `93ef2c5c53069deafe45055b5bfd093933108e223867938720b515835d493dde` |
| T3-PY 回执 | `6466eaee26c932c947420c433be105c789cd434ffd0ba910109e06994c5a1980` |
| 裸命令定位诊断回执 | `474c1026a40bc98eedaa846c1185a8f058bbc2294d318bc6c0de04e917ed5357` |
| 无线程 SDK 构建对照回执 | `e368495ebda90e7d9244d248f440460baf9eca411ca6b698924f247dadc6a48d` |
