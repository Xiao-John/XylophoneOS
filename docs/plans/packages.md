# 第三方用户态开发与包管理计划

2026-10-25，0035完成P0，0044完成受限P1。包管理器正式名称为 **xypm**，
命令为`xypm`，包ID为`xos.xypm`；不保留旧的xpm/xpkg命令别名。`.xpk`包扩展名、
v1容器/schema保持不变。历史日志、旧SDK与发行附件保留当时名称和哈希。

现有交付：独立SDK项目构建/打包/校验、宿主离线候选盘安装/升级/移除/归属校验、
客体list/info，以及P2的客体验证、事务和恢复。仓库分发留给P3。
见[0044验收与交接](../history/packages.md#log-0044_xypm_p1)和[开发快速开始](../friend_user_program_quickstart.md)。

## P1现在可用

宿主命令在XOS仓库目录执行；先关闭使用源盘的QEMU。输出必须是新文件，源盘
只读复制、全会话排他锁定，事务在私有候选盘内进行，完整回读验证后才发布输出。
不自动替换日常工作盘，也不自动重启QEMU。

```sh
python3 scripts/xypm.py install app.xpk --image source.img --output-image installed.img --offline
python3 scripts/xypm.py list --image installed.img
python3 scripts/xypm.py info friends.hello_friend --image installed.img
python3 scripts/xypm.py verify-installed --image installed.img
python3 scripts/xypm.py upgrade newer.xpk --image installed.img --output-image upgraded.img --offline
python3 scripts/xypm.py remove friends.hello_friend --image upgraded.img --output-image removed.img --offline
```

各命令用`--profile <file>`选择与包和数据库一致的冻结profile；缺省仍是P0发行
单线程profile。升级使用明确选择的包，依赖按版本/revision/包SHA256精确匹配，
不做版本范围求解或自动下载。拒绝未归属文件覆盖、大小写/父路径/真实FAT别名
冲突、已修改的归属文件及破坏反向依赖的操作。最多64包/8192归属文件，数据库
上限1 MiB。保留卸载目录内用户文件，只清理本工具原先创建且已经为空的目录。

数据库位于`/var/lib/xypm/db.json`，只读查询投影为同目录`index.tsv`，首行为
`xypm-index-v1`。旧名数据库/index存在时拒绝查询和事务，避免双重归属；当前没有
自动迁移器，应保留原盘并在独立副本迁移或重新创建测试盘，不直接改目录名冒充迁移。

原生程序独立构建为包内`/usr/bin/xypm`，不进入内核或启动模块清单：

```sh
python3 scripts/build_xypm.py --sdk /absolute/path/to/frozen_sdk --profile config/package/xos_x86_64_static_single_b2_v1.json
```

| 客体命令/行为 | xsh直接调用 | dash调用 |
|---|---|---|
| `xypm --help` / `--version` | 退出0 | 退出0 |
| `xypm list` / `info <id>` | 已装查询退出0 | 同一程序、同一结果 |
| `xypm verify <package.xpk> [sha256]` | 有界包结构/清单/逐文件摘要核验，成功退出0 | 同一客体程序 |
| `xypm plan install|upgrade <package.xpk>` / `plan remove <id>` | 只读预检；移除计划检查反向依赖；不写入文件或授权worker | 同一客体程序 |
| 不存在的包 | 退出1，stderr诊断 | 退出1，可读`$?` |
| 不支持的命令/参数 | 退出2 | 退出2 |
| 数据库/index错误 | 退出3 | 同一程序错误契约；损坏输入专项客体未单独验 |
| stdout/stderr重定向 | 沿用xsh当前语法边界 | B2支持`>`和`2>`，后续命令stdout恢复 |

原生list/info只展示投影，不能代替宿主`verify-installed`的完整归属文件校验。
此表同步公共外部命令契约，不给xsh添加dash语法，也不把dash B2扩成管道/子Shell。
本组实际验收16组P0宿主、12组P1宿主、10组双Shell/重启客体，资源恢复
`[129833,2,0]`；没有重跑旧压力或修改CPython/线程移植线。

宿主导出临时文件曾出现重名失败：`Disk.export()` 现在使用会话级 uuid 前缀和
递增 serial，宿主端以排他创建拒绝覆盖；失败样本保留在
`build/package_p1/xypm_acceptance/export_collision_failure.json`，修复后完整
验收通过。

### SDK边界

P0发行完整SDK仍绑定旧profile。B2新增`xos-x86_64-static-single-b2-v1`，
只为已验系统`911184be3f3c99f6`的单线程CRT/stdio转交注册冻结快照，补入旧完整
SDK的单线程C++归档及相应许可。SDK树哈希、组合方法与真实失败见0044记录。
新原生xypm声明`stdio_transfer`，必须用该profile构建才获得本组dash重定向证据。
旧SDK程序能启动并不保证它理解B2标准流转交。该profile不包含pthread/thread-safe
承诺，不借用CPython线的`build/threading_sdk`或自动登记新库。

## P2分段与当前实现

0048先落地P2-1：通用进程准入屏障、一个worker的文件写租约、成功清理释放、
失败关闭与显式恢复工作入口。新客体8项定向通过；它不修改包文件，也不替代
多文件事务。接口/权限见[e04_loader_sdk.md](../e04_loader_sdk.md)，命令见
[maintenance](../usage/supervisor/maintenance.md)。

P2-2增加客体 `verify`、`plan install|upgrade` 与 `plan remove`。包校验在同一只读打开句柄上
流式处理包字节，限制 manifest 1 MiB、单文件64 MiB、payload 256 MiB、8192个成员和
ustar archive 上限；拒绝重复JSON键、非UTF-8、非整数数值、超深结构、链接/扩展成员、
路径/大小/哈希不匹配和不符合本次编译profile的包。计划阶段解析数据库和index投影，
校验数据库SHA绑定、profile、依赖锁/依赖环、全局文件归属、已安装文件内容摘要、
目标路径父项及FatFs目录项规范名。计划命令不写文件、不执行payload、不授权进程。

P2-2已实现按宿主 `inspect_elf` 规则编写的客体 ELF64/x86-64 程序头、PT_LOAD/PT_TLS边界、
装载页重叠/地址区间、入口和页预算检查。该检查仍随包payload摘要核验流式执行，不解包
到目标目录。变更由冻结 `xos-x86_64-static-single-b2-v1` SDK构建/打包通过，详见
[0055工作记录](../history/packages.md#log-0055_xypm_p2_elf_validation)。新增共享输入、数据库与双Shell检查见[0066](../work_log/0066_xypm_p2_validation.md)。

P2-3/4已实现：安装、升级、移除在维护会话中校验原包并固定打开实例，准备新文件和
旧文件备份、同步发布journal，执行变更后记录commit；启动恢复器来自系统内置镜像，
即使磁盘上的xypm缺失也能回滚或清理。监督器检查`transaction`、`txdata`和
`transaction_commit`，状态异常或无法读取时保留门禁。损坏或不一致材料保留供诊断，
不得手动删除标记冒充恢复。可运行`maint-recover-boot`，也可显式运行`xypm recover`。

现有验证覆盖真实客体安装/升级/移除、满盘、日志损坏、启动恢复和逐点进程中断；
具体构建、测试结果及未覆盖范围见[0066](../work_log/0066_xypm_p2_validation.md)。
这些检查不构成突然断电、设备写缓存丢失或扇区撕裂的保证。最终P2验收以该记录中
对应最终源码构建的限定范围验收已通过；P3网络前/网络后工作仍按下文独立推进。

## P0现在可用

从XOS仓库目录运行，PROJECT指定尚不存在的仓库外目录：

```sh
SDK="$PWD/build/releases/0.0.1-1024/xylophoneos_revival_0.0.1-1024_sdk"
PROJECT=/tmp/xos_hello_friend
python3 scripts/xos_app.py init "$PROJECT" --id friends.hello_friend --language cpp
python3 scripts/xos_app.py build "$PROJECT" --sdk "$SDK"
python3 scripts/xos_app.py check "$PROJECT" --sdk "$SDK"
python3 scripts/xos_app.py pack "$PROJECT" --sdk "$SDK" -o "$PROJECT/dist/hello_friend.xpk"
python3 scripts/xypm.py inspect "$PROJECT/dist/hello_friend.xpk"
python3 scripts/xypm.py verify "$PROJECT/dist/hello_friend.xpk" --profile config/package/xos_x86_64_static_single_v1.json
```

输出已存在则拒绝覆盖；源码/资源/SDK或构建器变化后须重新build，不能把旧ELF当
本次结果。SDK必须是完整发行SDK目录，当前只登记该冻结快照的1046文件摘要；
不是任意build/sdk或任意同版本SDK。不要混入头/库或修改SDK；新profile由后续SDK
回执显式登记。可通过全局--profile指定另一个经审核的profile，不能用自填字段
冒充客体兼容证明。编译器固定x86_64-elf GCC/G++16.2.0；外部头/库注入环境变量
被拒绝，构建命令使用固定CRT/静态库，回执保存真实编译器/输入/产物摘要。

P0正式字段见config/package/app_v1.schema.json和xpk_v1.schema.json；语义校验由
scripts/xypm_format.py执行（路径、重复key、文件归属冲突、总大小、摘要等并非
仅JSON Schema能表达）。普通应用模板选择Apache-2.0，可自行改许可证；打包自动
随附该SDK真实声明，材料携带不等于逐库成员合规审计。默认包还带本例源码。

高级端口可先准备完整stage树及manifest，用宿主`xypm.py pack --root <stage>
--manifest <manifest.json> -o <out.xpk>`复用同一容器；不要求改为简单项目模板。
inspect/verify完整流式校验payload、executable的受限ELF布局；不执行包内容。
不带--profile时只检查格式/完整性，带它才检查声明profile/features；二者都不是
签名、运行授权或对任意外部ELF来源的ABI证明。--sha256可要求预先可信的整包摘要。

P0归档只含普通文件，目录由路径隐含，拒绝显式目录成员及所有链接/扩展；为避开
FAT显式短名别名拒绝`~`，路径限定ASCII字母/数字/下划线/点/加减号及斜杠，且必须
可由ustar name/prefix表示。P1已针对实际盘检查既有LFN/短名与归属冲突；P0包内检查仍不能代替它。
后文保留完整设计，P2/P3尚待实施。

0035证据：16组宿主测试通过，真实仓库外C/C++构建/重复打包；经已有文件桥把
两个包的payload传到全新盘，在冻结系统2c3876e640840ff5运行退出0，各自资源
回到[130342,2,0]。证据build/package_p0/，工作记录0035；这是新包payload运行
gate，不是通用安装器验收，未重跑旧压力或重建内核。

## 开发入口与边界

普通应用在独立目录/仓库开发，用版本化SDK编译，不修改XOS源码、user_build.py
程序清单或启动镜像。内建服务/系统夹具才进入系统构建。宿主交叉构建与XOS原生
构建都输出静态用户ELF；本地开发继续exec-file /out/app.elf，不强迫先打包安装。

宿主xos_app已提供init/build/check/pack，客体xypm已有只读查询，客体安装留到P2。发行SDK
compile.py和已有离线传输继续可用。工具不默认改日常盘、启动QEMU或授权。

```text
hello_friend/          # XOS仓库以外
  xos_app.json         # 已实现的项目声明
  src/main.c
  assets/
  licenses/
  build/               # 可重建对象、ELF与构建回执
  dist/                # 包、摘要和分发材料
```

描述文件记录源文件、C/C++模式、SDK profile、资源与安装清单；先支持显式清单，
不自造大型构建系统。复杂上游仍使用自己的构建系统/ports补丁，最终输出同一种包。
构建依赖与运行依赖分开，不把GCC作为普通静态应用的客体运行依赖。

ELF格式可解析、XOS ABI兼容、包可安装和这次能启动分别检查。P0建立机器可读
profile：架构/字节序/位宽、syscall ABI、startup版本、地址布局、静态TLS布局、
运行库single/threaded模型和真实feature集合。SDK及系统各提供匹配回执；初期只
接受明确登记兼容的profile，不凭OS版本大小或x86_64-elf target推断兼容。
SDK manifest摘要记来源，ABI profile ID记兼容约束，不因无关源码改动乱增ABI。
线程T0有布局变更时发布新profile；旧SDK/ELF保留回执，不能只换头文件混库。
Shell U0/U1已提供UTF-8行编辑与argv字节传递；manifest显示名/说明可用UTF-8，
路径仍按U2之前的ASCII子集，不能因Shell已支持UTF-8就允许文件服务尚不支持的
文件名。文档/数据内容可保存UTF-8；包路径Unicode化等U2实际通过后再启用。
静态libc/libstdc++随ELF发布，SDK更新不会自动修复已安装静态应用，需重建应用包。

安装不执行程序、不授予spawn/块设备/supervisor权限。包可声明所需能力供规划
检查，不能自行授权。普通应用无构造权；需要构造子进程的工具由独立、绑定内容
摘要的启动策略显式批准，该策略另验。现有exd/dash profile保持已有语义；路径、
包名或发行者字符串不成为内核身份。当前无完整用户/ACL，包文件归属只防误覆盖，
不宣称能阻挡任意恶意用户进程；签名也不等于沙箱或运行授权。

## 包格式：P0 v1普通文件子集已冻结

.xpk v1采用未压缩POSIX ustar子集与UTF-8 JSON manifest，复用容器，不要求zlib、
CPython、Shell脚本或数据库。宿主用Python标准库生成，客体用有界解析器流式处理。
归档/依赖/包数据库全在用户态，内核不认识包名或包版本。

manifest.json是第一个成员，后面为payload/内的普通文件。manifest列最终
相对根路径、类型、长度与SHA-256；payload路径对应清单路径。成员一一对应，禁止
多余/重复/截断项。manifest自身不自含哈希；整个包摘要在包外发布，安装可指定
可信的预期摘要。内部文件校验不能自行证明发布者身份。

首版拒绝软硬链接、设备、FIFO、sparse、PAX/GNU扩展和未知type；校验tar header
checksum、数字溢出、name/prefix拼接与终止块。不能直接任意tar extract到根目录。
不应用uid/gid/setuid/mtime/权限位：当前平台没有这些完整语义。未来压缩/签名或
扩展类型必须显式版本化和单独测试。

manifest至少包括format_version、id、upstream_version、revision、target_profile、
required_features、build_receipt摘要、runtime_dependencies、files，以及license/
source/修改说明。id为小写ASCII命名空间，如friends.hello；上游版本是不透明
字符串，revision为非负整数。首版不按字典序比较任意版本，升级显式选择包摘要；
运行依赖固定id+版本+revision+摘要，不实现SAT或自动择新。

以下示意字段使用实际v1结构；摘要/大小为占位，不是可安装样包：

```json
{
  "format_version": 1,
  "id": "friends.hello",
  "upstream_version": "1.0",
  "revision": 1,
  "target_profile": "<冻结的profile-id>",
  "required_features": ["file_io"],
  "runtime_dependencies": [],
  "files": [
    {"path": "usr/bin/hello_friend", "type": "file", "size": 12345,
     "sha256": "<实际64位十六进制摘要>", "role": "executable"}
  ],
  "licenses": ["usr/share/licenses/friends.hello/LICENSE"],
  "build_receipt": {"path": "usr/share/friends.hello/build_receipt.json",
                    "sha256": "<实际回执摘要>"},
  "source": "<对应源码来源与摘要>"
}
```

完整包也要在files中列license等随包文件。JSON禁止重复key、无效UTF-8、深嵌套
和无法精确表示的长度；大小为受限非负整数。首版预算：manifest 1 MiB，8192成员，
payload总量256 MiB、单文件64 MiB、元数据嵌套8层。流式处理不整体读入堆；P0用
CPython/工具包实际清单核验预算，超界拒绝，修改预算同步schema和gate。

## 布局、文件归属和依赖

| 路径 | 用途 |
|---|---|
| /usr/bin | PATH中的程序；复用当前PATH |
| /usr/lib/<软件名> | 私有运行资源，如Python标准库，不代表支持动态库 |
| /usr/share/<软件名>、/usr/share/licenses/<包id> | 资源、帮助、许可 |
| /var/lib/xypm | 持久安装数据库、事务及恢复材料，普通包禁写 |
| /var/cache/xypm | 可删除缓存，不存唯一回执 |
| /src、/out及应用数据目录 | 开发和用户数据，卸载不自动删除 |

首版只安装/usr下的声明文件/目录，不触碰boot/kernel、/sysroot、/etc、/dev或
/var状态。系统/SDK更新另批规划；应用状态由运行时创建并归用户管理，未来配置
文件要另有保留/合并规则。安装清单路径不直接接受任意prefix改写。

路径相对根，拒绝绝对路径、空/点/点点组件、反斜杠、控制字符、保留恢复名、尾点/
尾空格和不支持字符。遵守协议长度和目录容量；检查父目录类型，按FAT实际大小写
折叠及8.3短名别名检查冲突。不能只比较字符串；无法可靠归一的包拒绝。

一个文件只归一个包，即使内容相同也不共享所有权；目录可共享，卸载只清由本包
创建、无人引用且为空的目录。不同包/未管理文件冲突则拒绝，首版不提供force覆盖。
升级只替换本包且内容仍匹配数据库摘要的文件；本地修改默认中止，保留原文与
冲突清单。卸载不删除被修改文件或用户数据。不能只靠mtime判断文件是否改过。

已有GCC/dash等标为unmanaged，仅通过显式import-receipt、逐文件摘要及目标profile
检查才能纳管，不能扫描/usr/bin猜归属；旧回执缺新字段时需显式迁移，不填假值。
运行依赖先为精确锁定DAG，缺包、循环、冲突、移除反向依赖报错。先单包无依赖
交付，再批量拓扑计划；计划全部预检不等于跨包原子事务，首版不隐式下载。
Python的pip/venv是语言层，不能改写xypm拥有的解释器/系统文件。

## 事务与恢复

安装器单写者，数据库记包摘要/文件原摘要、依赖、SDK/profile、来源/许可与事务
状态。list/info/verify只读可先交付。源包在验证至复制期间保持同一文件读锁。

P1宿主离线安装：QEMU关闭，对源普通镜像持有整个会话排他锁，创建独立候选镜像；
在候选上完成校验/安装/数据库更新和sync，再导出新镜像。失败保留源镜像；首版
不原地替换原盘。拒绝设备/符号链接，复制前后检查源身份/摘要；逐文件短暂锁不能
替代事务排他。现有work_disk.py只是单文件桥，没有这套事务或数据库。

P2客体安装：先进入用户态监督协调的维护会话，拒绝新普通启动，确认没有其他
应用或构造中应用，只有监督/文件/包管理；关闭普通用户写入并取得整次事务排他。
没有该机制不得开放升级/卸载。内核只做必要机制，不识别包对象。包内无安装脚本、
postinst/hooks，安装器不启动任意payload或下载缺项。

事务状态validated→staged→applying→committed→cleaned：

1. 预检ABI、依赖、归属、路径、容量与新文件+旧备份+日志+数据库的空间。
2. staging、旧备份和操作意图先持久化，再逐文件rename/替换；remove也先备份。
3. 最后提交数据库，commit记录持久后才删备份。记录每步，恢复可重复执行。
4. 重启先恢复再开放新变更：已commit清尾，未commit回滚。日志/备份损坏或恢复
   失败保留诊断与材料，拒绝新事务，不猜测删除用户文件。

这是维护会话下的多文件恢复，不是全包同时原子可见，也不自动保证FAT任意掉电
不损坏。现有单文件staging不是包事务。P2先验进程终止及正常sync/重启；任意
断电/扇区撕裂保证另由专人故障测试，未测写not_run，只用专用盘。

## 批次与排期

| 批次 | 交付 | 定向验收 |
|---|---|---|
| P0 | profile/schema、独立项目模板、SDK build/check/pack工具 | 仓库外C/C++构建；无需系统改动；SDK错误、畸形包、路径/大小写别名、容量拒绝；许可/来源回执 |
| P1 | 宿主打包/查询/校验/候选盘安装；先新装，随后升级/移除/依赖和receipt迁移 | 包→新盘→XOS执行；冲突/满盘/失败源盘不变；重启、归属与原文/本地修改保护 |
| P2 | 原生单线程xypm，维护会话、事务/恢复、安装升级移除 | 排他拒绝；每步中止恢复；commit前后重启；恢复幂等；ABI/授权不能被包绕过 |
| P3 | 离线仓库索引/锁定；后续签名/密钥轮换及网络镜像 | 可信根、包/索引绑定、撤销/回滚/重放/混版拒绝，实际时钟/网络条件单列 |

0035起线程实施由朋友在PR交付，当前本线优先P0/P1，不抢其内核/SDK范围。P2不依赖多线程、
fork或CPython，先写原生单线程工具。先用hello_friend和一个已验工具演示，不把
整个GNU工具链纳管作为起跑条件；打包成功不提升dash/CPython/Qt功能支持等级。
P0/P1已通过本文列出的受限gate；receipt显式纳管、跨包批量事务仍未交付。
P2客体事务已实现，最终验收与限制见工作记录；仓库P3仍未完成。

P3复用成熟更新设计，研究TUF等现成方案，不发明签名算法。P1摘要只提供完整性，
人工核验来源的本地包可先用，不能称为已认证仓库。可信根、签名/防回滚及时间
依赖在对应批次实际验证再冻结，不让在线仓库阻塞离线第一包。

### P3按网络依赖拆分（规划，尚未验收）

**有网络前可做**：本地仓库生成和读取有界索引；按明确选择的包版本、revision、
profile和SHA-256生成与校验可重复的锁文件；从用户提供的本地包核对索引与锁文件，
拒绝缺包、混版、摘要不符及不满足精确依赖。离线可信根配置、成熟签名方案的签名与
校验、密钥轮换、撤销及持久版本防回滚也不依赖网络，但需单独选定实现和威胁模型，
证明密钥与持久状态的保护；可靠时间不可用时不能声称过期或冻结攻击已被检测。
宿主工具与客体实现、密钥操作、恢复/重放行为各自记录实际证据。

**需要网络后才能完成**：客体网络设备和协议栈、DNS、连接及TLS，仓库镜像访问、
自动拉取/更新、超时重试及镜像故障处理，以及在线环境下的传输、恢复与安全验收。
可信时间及其来源需要独立建设和验证；仅有网络或RTC不自动使时钟可信。在线功能
不能以宿主代下载冒充客体网络，离线摘要也不能冒充发布者认证。

## 首批真实包样本

- hello_friend：最小独立C/C++项目，验证仓库外构建→打包→安装→运行→移除。
- CPython：复用0030静态解释器与558文件标准库清单，验证多文件、版本化目录、
  容量/路径/许可；PY0已通过，但包安装不把REPL、完整标准库或真实线程写成已验。
- Open Adventure：复用[移植计划](adventure.md)及该线最终回执。Python/
  YAML生成器是构建依赖；若数据已编进dungeon.c/h并静态链接，游戏运行包不强加
  CPython依赖。源码/翻译/生成材料随适用许可交付；存档留在包外，升级/卸载不删。
  中文输出/英文输入复用当前UTF-8通道，存档路径先ASCII；不冒认该游戏已移植完成。

资源路径不能靠恰好从源码目录启动才能找到：按上游实际方式配置/usr/share下的
已安装路径，或编入只读映像，分别记录。不得为迁就打包把用户要求的客体生成/
编译步骤换成宿主代生成。SDK交叉构建、客体原生构建、可安装包是三个独立结果。

## 文件和交付职责

P0已建立scripts/xos_app.py、scripts/xypm.py、共享xypm_format.py和config/package/；
后续按实际需要扩展。scripts/xos_app.py与scripts/xypm.py为
宿主工具，复用SDK/FatFs后端；src/user/programs/xypm.cpp为客体只读命令，通用解析/事务
按职责放用户态库。两端共用schema/畸形包夹具，宿主Python不成为客体运行依赖。
SHA-256/JSON解析优先审查适合静态环境的成熟实现，保留来源和许可。

公共ABI由线程主端协调，打包agent不另定义一套。实施另登记范围；tests/package_*
只跑新增/受影响gate，压力专人负责。回执记录SDK/profile、源码/补丁、命令、包/
系统/盘摘要、结果、失败/未运行和恢复材料。正式分发带实际适用许可、源码/补丁
与构建材料；自研Apache-2.0不覆盖第三方或开发者自行选择的应用许可。

参考：[TUF规范](https://theupdateframework.github.io/specification/latest/)用于后续
更新安全选型，不规定XOS包格式或替代安装事务。
