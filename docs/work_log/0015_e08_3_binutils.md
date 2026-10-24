# 0015：E08-3 原生 binutils

状态：受限E08-3验收已通过，最终绑定5276ff16bb6470b0。
真正GNU工具在XOS内汇编/归档/建索引/链接/strip，并在XOS执行生成产物。
下文失败/修复段保留过程；最终证据和阶段边界见末尾。

## 文件责任与来源

main负责 tests/binutils_smoke.py、tests/fixtures/binutils/、Makefile集成与共享文档。
loader Luna负责 scripts/build_binutils.py、src/ports/binutils/，只在专属缓存构建。
源包GNU Binutils 2.47，实际SHA256
`154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff`。
捆绑zlib 1.3.1静态使用，GNU/zlib原许可保留；不使用宿主动态zlib。
新自研内容Apache-2.0，上游上下文与修改后GNU文件保留原条款。

build=arm64 macOS，host使用上游接受的x86_64-unknown-elf配置别名，target=x86_64-elf；
host别名不是Linux ABI。包装交叉编译器显式链接XOS CRT、SDK、newlib与libgcc；
宿主只生成Seed和离线安装文件，不在宿主执行XOS工具。

## 构建暴露的问题

- SDK getopt.h的include优先级遮蔽GNU私有头：调整顺序。
- XOS无symlink/lstat与POSIX mode：上游最小移植补丁按真实文件模型适配。
- gettimeofday无墙钟明确ENOSYS；避免libiberty回退的abort路径。
- 头文件声明不能证明实现存在：access/sysconf/dup按实际语义补齐。
- 自研mkstemp与newlib整对象重复：删除自研实现，复用newlib的_open_r/_stat_r/
  _getpid_r路径；不用weak符号或允许重复定义掩盖。
- GNU可选文件时间复制不能静默宣称完成，缺少设置接口时给诊断并记录限制。
- ld/plugin.c在2.47仍无条件编入，--disable-plugins只关闭BFD支持；XOS-only
  补丁显式拒绝-plugin，默认无插件路径不调用dlfcn，不造公开API stub。

首次as客体预检使用a817构建中的真实as-new：`--version`触发fault14，
RIP=0x4005c289、CR2=0。宿主反汇编定位bfd_init的`mov %fs:0`；BFD配置
compile-only检测将编译器TLS支持误当运行时TLS可用，产生.tbss。
报告build/as_preflight_report.json明确为失败且只属as预检，不是E08-3完成。
上游支持ac_cv_tls=none关闭TLS；它还需导出给递归子配置，不能只写顶层cache。
Seed检查已增加PT_TLS/.tdata/.tbss拒绝，后续须无TLS完全重编并在客体复验。

无TLS Seed ba58ebf8…首次完整客体链路：五工具--version正常、as/无索引ar/
ranlib返回0，ld异常拒绝且误报输入与输出相同。初步怀疑stat身份为0，
进一步检查ldlang.c确认该处比较lrealpath结果；反汇编lrealpath仅一条ret。
上游在无realpath/canonicalize且非Windows的分支漏了return，产生不确定返回值。
正在补有分配/失败语义的strdup回退，不绕过GNU的same-file保护。
stat/fstat身份全0是另一个独立缺项，亦用真实FatFs目录项位置及有界唯一inode
映射补齐，保持预构建newlib的16位ino_t ABI，不能把初步推断当作已证明根因。
新的runtime探针要求case别名一致、stat/fstat一致、不同文件不同、rename保持身份；
binutils测试另要求真正相同输入/输出被拒绝且随后正常链接成功。

E08-2构建6248c0c2803bdeaa的5组runtime测试已验证newlib mkstemp、dup共享偏移、
关闭一个fd后另一个仍可用以及原有完整驱动链路。新SDK快照为
`.cache/xos_seed/sdk_snapshots/ded6e4d4aca4d2dce7197f42611eaa94f197a78d885db4188eaba79a6c4ead15`，
manifest SHA256即目录名；此前快照只能用于历史失败追溯。

## 验收方式与过程记录

tests/binutils_smoke.py显式接收Seed manifest，核对工具与链接runtime哈希，临时盘
导入工具与保存源码；真实客体连续两轮as/ar/ranlib/ld/strip并执行ELF返回42，
检查汇编/链接错误非零和可见诊断、每步资源回收、源码逐字节保留、sync重启。
宿主readelf/nm仅静态检查导出的产物与archive索引，不代执行Seed。
ar使用rcS刻意不建索引，以独立只读probe核对GNU archive首成员从无索引变成
ranlib写入的索引，再链接并导出nm确认。真实2.47 ld支持此处无索引归档，不能
要求它必报错；早先测试的“index”匹配还可误匹配echo命令中的no_index文件名，
已改为只在移除命令echo后的实际诊断中匹配，不能保留该项为缺索引错误证据。
最终统一make smoke、材料检查和重建哈希的结果见末尾，不以中间失败报告冒充通过。

localpilot未扫描/修改；原日常盘不动。未提交/推送/读取凭据。

## 最终验收与交接

构建 `5276ff16bb6470b0`；源码SHA256 `5276ff16bb6470b0b5dd25b3516e819929e617a8f74147e0205440ed4085a110`。

- `make smoke`：79组通过，另7份许可材料检查通过。
- `python3 tests/binutils_smoke.py --seed-manifest .cache/xos_seed/binutils/build/47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e/manifest.json`：7组通过、32次真实客体命令；五个GNU工具均在XOS运行。
- 两轮as/ar/ranlib/ld/strip完整链路均执行输出seed chain、退出42。独立probe核对archive索引从无到有，宿主nm再核对；真正同输入/输出、错误汇编、未定义符号及显式plugin均非零且有实际诊断，源码逐字节未改，每步页/任务/完成记录回到基线。
- sync后关闭QEMU、再次启动，客体生成的stripped ELF仍输出seed chain、退出42。
- 同源码再次`make build`，完整manifest相同；193个产物和260个源码哈希实算一致。此项是XOS集成构建重建，不假报GNU完全清理重编的位一致性。

Seed构建指纹`47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e`，manifest SHA256 `1673edded076b3a8e001fc538ec52a452c38d4f2a7a115e7190fbdc2f69f3ef0`；
SDK快照`765f556c7ca8b70b1f91989a6063496a2686343ef4875b6edd3ce1aa31ad5a50`，实际CRT、库、链接脚本逐项与当前SDK一致。
主构建ID随测试文件变化，不能仅因SDK快照metadata的旧ID不同就误判输入不同；
验收脚本实际比较链接输入哈希。源码包、六补丁、GCC/libgcc及GNU/zlib许可哈希都在Seed manifest。

| GNU工具 | 字节 | SHA256 |
|---|---:|---|
| as | 2882480 | 792c04d9b39c3e6423d9fce5b04d6f6678d4330883a905c288c53f59751833d7 |
| ld | 3506496 | bdbdca011fa273beffe0146dd38304e7a581938133f737e839d6177a471501e9 |
| ar | 2066880 | cd75dcd55a78820717e877bbd031c8848e7d82766b96066b1e60ff0ea9fbd905 |
| ranlib | 2053768 | 332c979f33d40a8e9f17e22b74b3a6306a7d43257e8ad2b4e493145279139f09 |
| strip | 2139384 | 59648d4bf4f1dedbadad88079f56f18d0891910b4c567fe23d0dde2f29e583cb |

| 产物 | 字节 | SHA256 |
|---|---:|---|
| start.o | 1192 | 38d66522afc2df7fbcb8bfb72ac7ea07ae533ce12d12bde315bbbace4b5af600 |
| answer.o | 704 | 2841b84d2de7ccb9fd53819d1a53090530bf1ebaf880a9b31ddacaeb5fd3abf8 |
| libanswer.a | 848 | 5f4a2fcc9966ffe0ee81702270746c827c07c149bf88d137e8bae9813091e15d |
| app.elf | 13008 | 28d43c7e7f2c547f0d57728639b3d4c408f37c831f2e708e63ad073d910899e6 |
| app_stripped.elf | 12648 | 313a2754b618bfd4c14d7e49f1bfcc1f00d54c916b202c0721e44851e0a759f3 |

| XOS产物 | SHA256 |
|---|---|
| kernel.elf | ae8c629e07b6842f8889009006ae2fbbf7c0b1ef7fc41b83a95af5b08e205a9f |
| kernel.bin | 1a6a0ca317a1943fc90c630dc77f9c75941823fe6458c271c43ebde3663ce1e7 |
| xos.img | 7f4e361efed1c8b40470b30bfdb859d7d95c7bea13cfbfa3504949f82b28513a |

正式证据：build/binutils_smoke_report.json、binutils_smoke_serial.log、binutils_reboot_serial.log、binutils_archive_symbols.txt、binutils_app*.readelf.txt、runtime_smoke_report.json、全部正式回归报告及e08_rebuild_check.json。早期as_preflight失败保留为历史诊断，不计最终gate。

完成矩阵：E08-2路径读源/写产物/子进程状态/错误与资源→runtime5组；E08-3五个真正GNU Seed→版本+32条命令及输入哈希；汇编/链接/归档/索引/strip正确→独立archive读、readelf/nm与执行42；失败不破坏源码→错误路径+导出逐字节比较；持久性→sync/重启后执行；固件/ISA/用户态边界→既有回归与第二ISA编译检查（不是移植）。

当前界限：仅固定QEMU/512MiB/单核、小型汇编项目；另四工具只静态检查，不称客体验收。没有原生GCC/G++、完整POSIX、动态链接、TLS、任意GNU选项、大型项目峰值或任意掉电保证；O11–O13不整体通过。GNU公开分发/逐成员许可追溯仍未完成。原日常盘、localpilot与凭据均未动；未提交/推送。

下一步先按用户要求讨论qt_port_assessment.md（Widgets/QML分开，仅建议）；后续开发依原计划E08-4 C Seed。三位Luna子代理已完成各自范围，没有残留编辑占用。

最终许可登记去除构建进行中状态，改为仅本地使用/公开分发审查未完成；据此重新绑定5276ff16bb6470b0，79+7组及材料检查、完整manifest/193产物/260源码重建核对全部再次通过。未改变运行时或Seed链接输入。
