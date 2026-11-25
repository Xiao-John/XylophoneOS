# xypm P3：离线仓库索引与精确锁 v1

2026-11-25。基线 `08f3e13ead01c0d8d7d535e9f85d7d94510c2b20`。
本契约覆盖 P3 的网络前索引、依赖锁和单包事务衔接。宿主及原生实现已交付；
真实 XOS 客体验收、签名/可信根/密钥轮换、防回滚持久状态和网络镜像各自单列。
不改变 syscall、IPC、线程、TLS、ELF、libc 或 `.xpk` v1 布局。

## 文件与预算

仓库目录包含 `index.json` 和 `<完整64位小写sha256>.xpk`。包路径完全由摘要推导，
元数据不能指定路径、URL、重定向或执行命令。构建器复制源包到新建私有目录，验证
复制后的实际字节，最后发布索引；已有输出拒绝覆盖，失败移除本次未完成的新目录。

索引和锁各限 1 MiB UTF-8 JSON、8 层嵌套，拒绝重复键、未知字段、浮点数、布尔数值
及非法 UTF-8。版本沿用 XPK 的 1–1024 个 Unicode 字符和无 NUL 规则。字段见
[索引 schema](../../config/package/repository_v1.schema.json) 和
[锁 schema](../../config/package/repository_lock_v1.schema.json)；排序、跨对象绑定等
语义检查由 Python/C++ 实现执行。

| 对象 | 字段和规则 |
|---|---|
| 索引 | `format_version=1`、`target_profile`、`packages`；一个索引只含一个 profile，最多 256 个包 |
| 包条目 | `id`、`upstream_version`、`revision`、`sha256`、`size`、`required_features`、`runtime_dependencies`；按摘要严格升序 |
| 包身份 | 版本为不透明字符串，revision 为 0–2147483647；同一 id/version/revision 的不同摘要拒绝为歧义输入 |
| 依赖 | 精确 id/version/revision/SHA-256，按 id 严格升序；最多 128 项；拒绝自身依赖 |
| features | 最多 64 个 profile feature，严格升序且唯一；与包内 manifest 再核对 |
| 锁 | `format_version=1`、`target_profile`、`index_sha256`、`roots`、`packages` |
| roots | 1–64 个明确选择的根包摘要，严格升序；工具不推测最新版本 |
| packages | 从 roots 和依赖确定性遍历得到的完整、依赖在前的摘要序列，最多 64 个包 |

锁用 `index_sha256` 绑定索引原始字节；索引中的精确身份、profile、features 和依赖
通过包的完整 SHA-256 与包内 manifest 交叉验证。白空格变化也需要重新生成锁。
锁不能省略依赖、增加无关包或重排解析结果；闭包中每个 id 只能选择一个版本。
缺根包、缺依赖、冲突版本、环、错误 profile、摘要/长度/manifest 不符均拒绝。
索引可以包含未被所选 roots 使用的其他版本；验证本次锁只读取所选完整闭包的包。

确定性顺序为 roots 按摘要排序，每个包的依赖按 id 排序，深度优先遍历，子依赖先入
结果，已访问的相同包只出现一次。版本号没有大小比较或范围求解。

## 命令与事务

宿主示例，显式选择与包相匹配的已登记 profile：

```sh
python3 scripts/xypm.py repo-create base.xpk app.xpk -o repo --profile profile.json
python3 scripts/xypm.py repo-lock repo "$APP_SHA256" -o lock.json --profile profile.json
python3 scripts/xypm.py repo-verify repo lock.json --profile profile.json
python3 scripts/xypm.py repo-plan repo lock.json --profile profile.json
python3 scripts/xypm.py repo-install repo lock.json friends.base --image source.img --output-image base.img --offline --profile profile.json
python3 scripts/xypm.py repo-install repo lock.json friends.app --image base.img --output-image app.img --offline --profile profile.json
```

`APP_SHA256` 是操作者明确选择的 app.xpk 完整摘要。`repo-lock` 输出精确锁及其摘要。
`repo-upgrade` 使用相同参数，显式选择已经安装的包升级。卸载沿用 `remove`；现有
反向依赖、已修改文件和归属检查保持有效。

原生 xypm 读取相同字节，不依赖 Python。仓库目录和锁使用规范的绝对 ASCII 路径，
目录最长 186 字节，构造后的包路径最长 255 字节；检查实际 FAT 目录项，拒绝短名
别名。XOS 文件服务当前不提供链接；宿主读取拒绝符号链接，核验打开实例的类型和长度。

```sh
xypm repo-verify /repo /out/lock.json
xypm repo-plan /repo /out/lock.json
maint-run /usr/bin/xypm repo-install /repo /out/lock.json friends.base
maint-run /usr/bin/xypm repo-install /repo /out/lock.json friends.app
maint-run /usr/bin/xypm repo-upgrade /repo /out/new_lock.json friends.app
```

两个实现的 verify、plan、install、upgrade 均接受 `--lock-sha256 <摘要>`，用于
验证独立可信渠道提供的锁字节摘要。未提供时仍验证索引、包和闭包的内部一致性。
普通 xsh/dash 进程可只读验证和查看顺序，写入继续要求维护写租约和恢复器 ABI。

`repo-plan` 展示锁的依赖顺序。每次 install/upgrade 先验证整个锁闭包，再将选定包
及精确摘要交给已有 P1/P2 单包事务；已有依赖必须先装好。P1 在私有候选盘中安装，
完整回读后发布新盘；P2 在原包的稳定打开句柄上再次校验选定摘要，然后保持该句柄
完成 staging。路径在两次验证间被替换会被重新校验或拒绝，实际安装字节必须通过校验。

每次事务保留维护屏障、数据库/投影一致性、反向依赖、文件归属、本地修改保护及恢复
流程。跨包原子更新、自动装完整闭包、自动挑选升级和自动移除旧依赖留待批量事务阶段。
需要同时改变互相精确锁定的已装包时，现有反向依赖检查会明确拒绝。
原生错误退出 3，参数错误退出 2，成功退出 0；宿主错误退出 1。验证和计划无写入副作用。

## 安全边界及审计修复

本版信任操作者控制仓库目录、选择 profile 和提供独立摘要，提供内容完整性及可重复
选择。发布者认证、密钥管理、撤销、持久版本防回滚、可信时间及冻结攻击检测仍按 P3
后续安全阶段设计和验收，本版没有自行实现签名算法。

宿主 `.xpk` 校验以 `O_NOFOLLOW | O_NONBLOCK` 打开后核验实际普通文件；读取上限
绑定打开实例的初始长度，末尾检查额外字节及实例元数据变化。FIFO、链接替换和持续
增长输入不会把尾部扫描变成无界读取。索引记录使用同一打开实例返回的长度。
原生对 header/member/padding/end 都在读取前核对捕获长度，并检查最终 EOF。

原生已有的排序 manifest 索引用于二分查找 payload，保留精确大小写和重复项检查，
把逐成员查找从 O(n²) 降至 O(n log n)。另修复 `ensure` 无需变更的返回路径残留指向
已失效栈帧的解析错误目标。

## 验收交接

```sh
python3 tests/package_p3_repository.py
ASAN_OPTIONS=detect_leaks=0 python3 tests/package_p3_repository.py --sanitize
python3 tests/package_p1_cases.py
python3 tests/xypm_json_cases.py
```

当前环境缺固定 x86_64-elf GCC/G++ 16.2.0、成套冻结 SDK 和 QEMU，原生代码仅进行
宿主编译/执行与完整程序语法检查。ASan/UBSan 已执行，LeakSanitizer 受 ptrace 环境
限制未执行。精确结果和命令见本组 work_log。

后续成员需用对应 profile 构建 `scripts/build_xypm.py`，在同版本系统和专用工作盘中
分别从 xsh/dash 运行有效/畸形仓库、pin 不符、缺包、冲突、依赖安装及升级/卸载，
验证未授权写入拒绝、维护恢复、资源回基线及重启后数据。还需把 P3 包衔接到 P2
逐点中断/满盘/恢复矩阵；记录系统/SDK/ELF/仓库/锁/盘摘要、工具版本和串口原始输出。
旧 P2 冻结报告保持原范围。
