# 0086：newlib UTF-8 代理码点

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-29。检查 newlib 4.6.0.20260123 源码发现：UTF-8 三字节解码路径检查
overlong 和续字节，但未排除 U+D800–U+DFFF；`wchar_t` 为 UCS-4 时编码路径也会为
代理码点生成三字节输出。两者与 XOS UTF-8 输入/输出的 Unicode 标量值边界不符。
这是源码审查结论，不是客体运行结果。

新增 `src/ports/newlib/patches/0001-reject-utf8-surrogates.patch`，只在隔离候选源码树
应用；解码拒绝代理范围，UCS-4 编码拒绝代理值并设置 EILSEQ。UTF-16 编码路径未改。
原有 vendored 二进制、已发行 SDK 和旧资格未改变；组件清单记录原包及补丁哈希，
原始声明保留。补丁 SHA256 `786dcff849e2c16fb02383a2e0cc7185bd963b378ef276b93bd15bda32c8291f`。
构建器回执记录补丁、命令及工具；宽字符探针增加 overlong、代理码点、超范围、分片
代理码点和 UCS-4 输出拒绝断言，尚未执行。

`python3 scripts/build_utf8_newlib.py --archive .cache/xos_seed/threading_sources/newlib-4.6.0.20260123.tar.gz --output ${XOS_SCRATCH}/xos_w1_newlib_strict_20261029 --jobs 8`
完成单线程与线程候选；libc SHA256 分别为
`75359f4594a01db330f3d7a1512ecb0ae60a6f94085f374ab459fa18787933bb` 和
`f7a4854017f9cfbaff90aa974c91c34185cbbf8f9438f5a140efe892ee5920c2`。
`python3 scripts/build_utf8_sdk_candidate.py --newlib-prefix ${XOS_SCRATCH}/xos_w1_newlib_strict_20261029/single/prefix --output ${XOS_SCRATCH}/xos_w1_utf8_strict_sdk_20261029`
构建成功，候选 SDK 树 SHA256 `db96154268cc796ef180ec621019f3cd1c89ba0b43bb041ec1b00a7e82c69b27`；
使用其 CRT 和静态库交叉链接探针得到 ELF SHA256
`d184db272ef1ba84728a34818d385ea79214a94442546c37bd8bb132d77f0ae0`。
随后补充低代理码点拒绝和合法四字节往返断言，重新链接的 ELF SHA256 为
`15cba1fb7d469269d69c421ab6d7dcc879f2dbb15a18372ebb82380b83e50c0b`。
这些均是提交前构建/链接结果，不是客体行为、UTF-8 或线程资格。

线程 SDK 构建进行时误启动了 `build/w1_surrogate_license_build_20261029` 系统构建，
违反公共 build 排他规则；发现后立即中断（退出 130），不使用其不完整产物或声称通过。
线程 SDK 构建结束后再以新的输出目录串行构建、检查许可。两者的输出路径不同，但不以
此抹去并发错误。

线程候选结束后，用其 SDK `compile.py --c` 交叉链接当前宽字符探针，成功；线程 SDK
manifest SHA256 `36a46b6e1a390f0cf80a39d48bcf3e1402b84a781f5efc8b7f021202628cbdef`，
探针 ELF SHA256 `c1eb6efbc5065e13501268ea5110d134b04965f06e4488e0e5e24e45eaeb0aae`。
线程候选和探针均未在客体运行，不宣称线程安全或 locale 行为通过。
随后串行构建 `build/w1_surrogate_license_serial_20261029`，build ID
`fe45eed2c40ef4a0`；`python3 scripts/license_audit.py --build build/w1_surrogate_license_serial_20261029`
检查 7 项许可材料通过，不等于逐成员许可审计或公开分发资格。

后续须以提交后匹配的 SDK 在客体执行断言，验证线程 profile、资源与终端端到端行为；
W1 输入所有权和等待、W2 ncursesw 依旧未完成。
