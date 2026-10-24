# E08-3：XOS-hosted GNU Binutils Seed

受限验收历史构建5276ff16bb6470b0；0017修复S2文件位置bug后的定向验证构建为
b1ded17e673ccffc，新Seed见下方命令；本轮未重跑全量gate。历史完整验收见0015，
本次修复与定向证据见0017、state.md与archive_link_regression_report.json。
这里说明构建、使用和接口边界，不声称GCC已移植。

## 构建与验收

源包GNU Binutils 2.47，版本/实际SHA256在src/ports/binutils/source_lock.json；
Canadian cross由scripts/build_binutils.py执行，arm64 macOS上交叉生成供XOS运行的
静态x86-64 ELF。SDK必须是经过核对的独立快照；脚本校验指定manifest SHA256，
记录CRT、SDK库、链接脚本、libgcc、编译器、补丁和最终工具的实际输入/输出哈希。

```sh
python3 scripts/build_binutils.py \
  --sdk .cache/xos_seed/sdk_snapshots/f187691498b56720feb7ee118ad6cd70b2808cd4145ad7d4ea3d640ee51a1a93 \
  --expected-sdk-manifest-sha256 f187691498b56720feb7ee118ad6cd70b2808cd4145ad7d4ea3d640ee51a1a93 \
  --jobs 10
make binutils-smoke SEED_MANIFEST=.cache/xos_seed/binutils/build/a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479/manifest.json
```

上面复用本轮已保存SDK快照和Seed；全新环境需先构建并复制独立SDK、计算其manifest
实际哈希，再使用脚本实际输出的构建指纹，不硬填历史哈希。普通make build/smoke
不联网构建GNU；binutils-smoke显式选择已准备Seed，在临时512MiB盘内安装、运行，
不修改日常盘，也不在宿主执行任何Seed。宿主readelf/nm仅静态检查导出产物。

测试依次运行as/ld/ar/ranlib/strip版本、两轮真正汇编/归档/建索引/链接/strip/执行。
ar rcS后独立只读检查无索引，ranlib后检查索引存在，再由nm核对导出索引；
GNU2.47可链接此处无索引归档，不用它必须报错的假设验证ranlib。
检查相同输入/输出拒绝且不损坏对象、汇编/链接错误非零、插件不支持诊断、
资源计数恢复、保存源码逐字节保留、sync重启后生成ELF仍可执行。

## 手工运行

工具由脚本安装到专属cache下install/usr/bin/x86_64-elf-*，不是只读启动模块。
在QEMU关闭时，可用work_disk.py显式导入某个测试盘的/bin/as、/bin/ld等名字；
该工具拒绝覆盖目标，已有目录也不自动清理。不要对正在挂载的镜像并发离线写入。
使用新的专用盘演示即可，日常盘不是验收材料。

```text
exec-file /bin/as --64 -o /out/start.o /src/start.s
exec-file /bin/as --64 -o /out/answer.o /src/answer.s
exec-file /bin/ar rcS /out/libanswer.a /out/answer.o
exec-file /bin/ranlib /out/libanswer.a
exec-file /bin/ld -T /src/app.ld -o /out/app.elf /out/start.o /out/libanswer.a
exec-file /out/app.elf
exec-file /bin/strip -o /out/app_stripped.elf /out/app.elf
exec-file /out/app_stripped.elf
sync
```

源码和链接脚本样本在tests/fixtures/binutils/。XOS目前静态用户地址窗口/堆区/
W^X规则见e08_runtime.md，不能把普通Linux ELF或默认链接地址直接当XOS程序。
这条链输出seed chain并返回42；是汇编开发闭环，尚没有C/GCC编译。

## 当前移植范围

使用上游支持的x86_64-unknown-elf作为host配置别名，不冒充Linux系统调用ABI。
递归configure共享实际runtime cache：无fork/vfork/mmap/TLS/dlfcn，不能以编译器
能生成某指令/重定位就声称内核运行时可用。Seed检查拒绝动态链接与TLS段/节。
工具单线程、无插件/NLS/系统压缩库；使用捆绑zlib 1.3.1静态实现。
FatFs没有符号链接、POSIX权限或时间设置；可选mode处理按真实平台跳过，显式
preserve-dates给不支持诊断。ld显式插件选项拒绝，不实现成功stub。
无realpath平台的上游lrealpath漏返回值通过最小strdup回退修复。

系统上界仍为512MiB物理、每任务65536页、8任务、每会话8个文件打开和全局16个
FatFs锁。newlib ino_t为16位，文件身份由服务按真实SFN目录项分配，root=1、
最多65534个非root身份，一次服务生命周期中不复用删除的编号，耗尽明确失败。
这些边界足够当前样本，不证明大项目链接、任意GNU选项、GCC/Qt峰值或完整POSIX。
2026-10-24压力测试进一步发现：34成员archive的final `ld`会报成员unknown
architecture，首个失败成员在不同运行中不稳定；host对象/archive有效，guest
`ar t`/`ld -r`可读。E08-3压力未全绿，见reports/e08_3_stress_report.md；
0017已修复libc普通open错误以文件大小初始化偏移的问题；新Seed使用新SDK，
保留现场的34成员archive最终链接/执行/strip回归通过，旧Seed仍含bug。
这不是完整压力重跑，也不证明任意大archive/GCC均可用。后续压力测试由专人负责。

## 许可证与交接

GNU/zlib原许可在src/ports/binutils/upstream/，XOS补丁与配置另存；新自研内容
Apache-2.0，GNU上下文保留原授权。SDK/工具清单和libgcc输入哈希随构建保存。
当前仅本地cache/临时验收盘，未公开发布GNU二进制；对应源码/例外/逐成员材料
的完整分发审查仍按licensing.md执行，不因材料检查就冒称全部审计完成。
