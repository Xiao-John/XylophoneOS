# ClarkE JSC 匿名配置页与真实冻结

基线 `7a3bab82`，配置源码 `b73f1f0f14e077cafb66065f928ec3a4efee528b`，
正例与冲突夹具 `731e62b9668f6290602ae926afa5b2b3202c5e23`。LLInt 的直接
取址及 GNU ELF 标签至 `adc77870d1927e801093f175a1369e91d90b6755`。
宿主沿用锁定 WPE WebKit 2.54.2、ICU 79.1 目标档和已验签源构建的 glibc C/C++
SDK，实际编译工具为 x86-64 目标 GCC/G++ 16.2.0 和 GNU binutils 2.47。

上游 `jscmain` 在 `JSC::initialize` 之前启用 restricted options 并解析参数。
`JSC::initializeWithOptionsCustomization` 随后运行 WTF 与 options 初始化、准备
解释器和结构堆。正常 VM 构造调用 `Config::finalize`。XOS 的早期构造器按 CRT
现有 `.init_array` 优先级运行，覆盖 shell 的提前访问。WTF 的常规入口继续调用
幂等的配置准备函数。

XOS 匿名 VM v1 arena 为 `[0x100000000000, 0x200000000000)`，页大小 4096。
本配置保留 16 KiB，首地址为 `0x1fffffffc000`，满足 WTF 布局对齐。
以 `PROT_NONE` 和 `MAP_FIXED_NOREPLACE` 精确保留，再提交为读写。
配置基址字面量存于真正的只读 ELF LOAD 段，代码从这里访问匿名数据区。
`Config::finalize` 使用真实 `mprotect` 把该区改为只读，地址碰撞或提交失败
在访问配置之前退出。同址现有映射保留原有 nonreplace 语义。

LLInt 的 XOS offlineasm 分支使用现有 `pcrtoaddr`。生成的 x86-64 指令先
对 `g_xos_jsc_config_address` 做 RIP 相对 `leaq`，再经 `movq` 读取只读
字面量，从所得地址使用原结构字段偏移。真实目标 settings 与 offsets 提取器
均为静态 x86-64 ELF，主机 Ruby 从这两份输出生成完整 `LLIntAssembly.h`。
两处 GNU ELF 宏使相同汇编进入真实 `LowLevelInterpreter.cpp.obj`。
生成头的 73 处配置读取全部在目标对象中对应 `R_X86_64_PC32`，无需中间 GOT。

上一分配器源码的普通 `cmake --build --target jsc --parallel 1` 在
`LLIntOffsetsExtractor.cpp` 触发宿主 OOM。当前配置把这一步保留为单作业，
采用 GCC `ggc-min-expand=5` 和 `ggc-min-heapsize=8192`。进程地址空间限为
660 MiB 时 GCC 仍报告内存不足；移动重复解包输入和把上限提高到约 992 MiB
后，实际生成器及目标汇编对象通过。完整 JavaScriptCore 归档、静态 shell
链接和脚本执行仍待验收。

## 原生权限与地址冲突

```sh
python3 src/ports/webkit/build_llint_layout.py --wtf-config \
  --archive "$WPE_ARCHIVE" --icu-archive "$XOS_ICU79_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output "$CONFIG_OUT"
python3 tests/qt6_sdk_probe.py --image "$XOS_PROBE_ISO" --payload "$CONFIG_ELF" \
  --marker CLARKE_WTF_CONFIG_FROZEN --report "$GUEST_REPORT"
python3 tests/qt6_sdk_probe.py --image "$XOS_PROBE_ISO" --payload "$COLLISION_ELF" \
  --marker "ClarkE JSC configuration mapping failed" --code 1 --report "$COLLISION_REPORT"
```

用正常目标编译规则重建 `WTFConfig.cpp` 及仍引用旧数组的
`MetaAllocator.cpp` 和 `Threading.cpp`。从已验 173 成员目标归档替换这三个
对象与已验原生 OSAllocator 对象。目标 `nm` 检查归档中没有旧
`g_config` 引用。按前一 WTF 夹具的静态链接命令链接新归档，地址冲突版加
`-DCLARKE_TEST_PREEXISTING_CONFIG=1`。两个 ELF 的基址符号均进入实际只读
LOAD 段，段内原始 u64 值一致。

QEMU 11.1.2 的同一普通 Xsh 镜像 `27b469b7e3c35968` 分别运行两份目标
静态 ELF。正例证明主函数前已得到零页，进行真实 WTF 初始化与 finalize，
通过内核写入 syscall 分别对冻结配置页和 ELF 基址字面量得到 EFAULT，
原值保持，退出 0。冲突版的 `.preinit_array` 先占用同一匿名地址，输出实际
预占标记，接着配置构造器输出明确错误并在主函数前退出 1。两次运行资源
前后均为 `[129698, 3, 1]`。这是 WTF 配置与 CRT 生命周期的证据。

| 工件 | SHA-256 |
| --- | --- |
| 配置对象构建回执 | `eaacdd6d7143de62b7c284db7bc5c5089fc0cb895b6113b59c3b508c36b9566a` |
| 配置目标对象 | `c24c9819f73d1d10580f721aabec034bfc0d8c08307441c8fcc8501b184011d9` |
| 173 成员配置归档 | `e0b8f18b17d383ad03bc416c4a6184f2b14b6c44177262c698f05da1d82a227f` |
| 正例目标 ELF | `e28f44da107b8cb65b5f8b262b70c03e9b55689ac94a988931ab06786244257e` |
| 冲突目标 ELF | `bad286308734ad060a6069149cf97814637fbf7d772f2fbd3db4e7a67cc9539a` |
| ELF 字面量核对 | `ddc1c15d769263480495c4f060b2af3617aeaa69efee16c53005e00042e7e119` |
| 正例客体回执 | `d25d082aee14773401e83f8cc108d03559a7b9f2af1c5e9f44e5b0c209dcb50b` |
| 冲突客体回执 | `7d1c99829f1881119e4ec09c5b83a544c60a4290709b5d544ec4581fe30a06dd` |
| 上一分配器代码的完整 JSC 编译尝试 | `04e6019e2644366f83ea6b8f77595ff6299938996b55575710c66294a275d4e4` |
| 目标 settings extractor | `7c92e8ef244076300536e4b651ac3d4c7547fe65a9c74b9fe00e6563501666d8` |
| 目标 offsets extractor | `ab93a3e3abc3cc0e8c455df98ff7c7c5028b2c54f93c81f80494a6494db4efc4` |
| 完整目标 LLIntAssembly.h | `e2eb748c1ae440d63fa5ac417641d5891af90559cc2d1871a315cffc017bd188` |
| 真正的 LLInt 目标对象 | `ef66e85b46eccb985bf37e864740b461089aa88c7b32358bdfd54a28fa59fc10` |
| 直接取址及目标重定位回执 | `ce2a082c555fc4df40defb5952c44965d1570c61cfb619f11fced45b36731faf` |
