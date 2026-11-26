# a5bbad87 · 静态 glibc 替换重链接材料样例

以冻结的 C/C++ SDK `d32a5c3b…` 编译一次 C 对象，使用实际 GCC 16.2 和 binutils 2.47。保留同一对象、链接脚本、CRT 和其余归档，只将 `libc.a` 从冻结版 `d3384b92…` 换为 #300 的签名 C SDK `e0016a3a…` 中的 `7ee8563f…`。两个 ELF 均为原生静态 TLS 程序。

在断网 Linux arm64 的 QEMU 11.1.3 上，从同一普通镜像 `17cebdf4873d898e` 运行两个 ELF。原库的访问、现存文件及缺失路径用例均得到 ENOSYS。替换库访问现存文件成功，现存非链接返回 EINVAL，缺失路径返回 ENOENT。两程序均退出 0，恢复至 129793 空闲页、2 个任务、0 个完成记录。停机后核对两个 ELF 和数据文件。
[客体回执](../reports/glibc_static_relink_materials_20261127/guest.json)
[#300 对应接口](ab3628db_glibc_canonical_path.md)

## 分发材料样例复验

本地样例归档 `glibc-static-relink-materials-20261127.tar` 包含应用源与对象、链接器输入和许可、两份 libc、glibc/GCC 上游归档和签名，以及各候选的 XOS 修改和构建输入。工作卷保留实际归档和独立解包目录。

独立断网容器只挂载该归档与全新输出目录。逐一校验 1,435 项文件，展开后分别从提供的对象重链接两份 ELF，字节与来宾运行的文件一致。还从归档内还原两个 SDK 的项目输入，分别复验 308 和 316 个实际输入摘要，在两组独立目录运行来源认证、补丁应用与目标配置，均到达 `configured`。
[打包及脱离原目录的复验](../reports/glibc_static_relink_materials_20261127/detached_materials.json)

```sh
tar -xf "$MATERIALS"
cd static-relink-materials
sha256sum -c SHA256SUMS
python3 relink_materials.py --runtime original --output ../original.elf
python3 relink_materials.py --runtime replacement --output ../replacement.elf
```

该样例覆盖一份外部静态 C 应用和两份 libc。完整 libc 重新编译、按最终产品生成对应材料、Qt 静态库成员级登记和额外应用重链接仍属正式发行门。默认 SDK、发行配置与冻结 newlib 路径维持现有状态。
