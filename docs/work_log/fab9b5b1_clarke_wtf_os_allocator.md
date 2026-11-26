# ClarkE WTF 原生匿名页分配

基线 `45fc232a`。分配器源码至 `fab9b5b14f4b91355bc413a0e4b4167fff478b4b`，
加入失败回滚检查后的夹具为 `1bbbf2e75f7d4da5937b722d1269b06d03a5e392`。
锁定 WPE WebKit 2.54.2 的真实 `OSAllocatorPOSIX.cpp` 使用现有 XOS VM ABI。
保留不计费，提交与页访问权限走目标 glibc 的 `mprotect`，原生 decommit 释放
物理页并保留虚拟区间。原有 release 路径通过真实 `munmap` 回收区间。

内核返回对齐后的基址。对齐覆盖 guard 时，分配器剔除满足可用区对齐的前缀，
保留紧邻可用区的两侧 guard。提交或剔除失败会回收刚取得的完整区间。
溢出、错误对齐、W+X 和未启用的 JIT cage 请求失败。普通 `zeroFill` 写入现有
可写区，访问权限由原来的保护控制。无可用的 madvise 提示时沿用可选 advisory
路径。ABI、内核与 SDK 保持原接口。

## 实际构建及证据

Linux arm64、GNU GCC/G++ 16.2.0 和 binutils 2.47，使用相同的
[锁定 WTF 运行库](73cec3d9_clarke_wtf_native_runtime.md)配套 SDK 和 ICU。
在已有构建入口加 `--wtf-allocator` 并指定新输出目录。静态客体链接采用
原先完整的 173 成员 WTF 归档，仅在独立归档中用原生新对象替换旧分配器对象。
用目标 `ar` 校验成员数量及替换对象的实际字节。其余 WTF 对象使用原文件，
旧薄归档及保留证据路径独立。夹具链接、静态 ELF 检查和普通 Xsh 启动使用
同一版 glibc C/C++ profile。宿主 QEMU 11.1.2 使用普通系统 `27b469b7e3c35968`。

```sh
python3 src/ports/webkit/build_llint_layout.py --wtf-allocator \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output "$ALLOCATOR_OUT"
python3 tests/qt6_sdk_probe.py --image "$XOS_PROBE_ISO" \
  --payload "$ALLOCATOR_ELF" --marker CLARKE_WTF_OS_ALLOCATOR_OK --report "$GUEST_REPORT"
```

实际夹具覆盖 `PageReservation` 的部分提交、真实访写、decommit 后计费下降、
重新提交得到零值、带前后 guard 的整体释放、带 guard 的 64 KiB 对齐和可重用
前缀、两页顺序访写、只读访问与恢复写权限、清零，以及 4 GiB 对齐的 4 GiB
稀疏保留与释放。错误输入保持原计费。独立直接调用确认 4097 页提交返回
`ENOMEM`，同样的提交经分配器失败后，原 guard 区间可再次精确保留。
来宾输出 `CLARKE_WTF_OS_ALLOCATOR_OK` 并退出 0，资源前后均为
`[129698, 3, 1]`。完整 JSC、VM 配置区冻结和 JavaScript 运行仍待单独验证。

| 工件 | SHA-256 |
| --- | --- |
| 原 WTF 薄归档 | `2e617217eabb9460c99844bb9a12ad04b340a6d8371c1806be60b75668f9fe28` |
| 目标构建回执 | `2179311b2266c16d0822c76b6d6c7ea2bd38c0ff53c9a29dd432915f79a76dbc` |
| 目标分配器对象 | `cd35477edf3d4b4bea4e424bf9781a5b0d0659745eae317944b3592e834e1c1b` |
| 新 173 成员归档 | `c3bf913846fcd401bf8225a96a8fa99dd2b864d3cab9e689abd48496c1c65b3f` |
| ISO | `ad502c5b9ba83bc1e96f33fdd56da82672c7e25feb344449b7c907d3cc8514e0` |
| 回滚夹具静态 ELF | `51cd52c92987911764464775246c225475b52e46be9a950f58ae2ab1db718aa4` |
| 最终来宾回执 | `38b9c07e978a976b23f2427edcfd67ab76ccac965d17923cfd1c59b6ec882e0a` |
| 最终串口记录 | `9dbba9a41131c29e1945f0c7acd0ad75b51c1728e5e4e70def5f3c964ffe3ca5` |
