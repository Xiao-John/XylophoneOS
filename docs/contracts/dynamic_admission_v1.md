# 原生动态身份与离线 generation 准入 v1

本页登记 `dynamic_abi.hpp` 和 `dynamic.hpp` 的实际元数据组件。它是
[D0](dynamic_linking_d0.md) 的一部分；**不使公开 spawn/exec 接受动态 ELF**，
不提供持久激活服务、发行签名、ready 协议、符号/重定位验证或动态 SDK 资格。
旧静态 ELF、startup v1/v2/v3、syscall 与文件操作布局保持原语义。

## 1. 信任边界

`inspect_identity` 检查一个已经选定对象的身份和 ELF 载体；`verify_object` 先从
同一个 readonly pin 读取完整内容、核 SHA-256 和长度，再检查该身份。所有读取由
调用方提供的 `elf::read_exact_fn` 完成。本组件不重新按路径打开文件。回调必须
持有同一不可写 pin，实施读取错误和启动总期限；可随意变换返回字节的回调不是 pin。

`read_generation` 一次读入最多 6272 字节的私有快照，在同一份字节上计算摘要和
解析结构。预期 generation ID、摘要和 SDK 摘要必须来自已绑定系统镜像的只读
根记录或独立认证的激活控制器。放在程序旁边的普通可写 JSON/二进制文件不会
自动获得信任。失败将输出清零，调用方不能继续使用未验证结构。

SDK 摘要和完整对象摘要保存在外部 generation 中；对象自身的 note 不包含
覆盖自己的完整文件摘要，以避免循环。`toolchain_abi` 是 SDK 发行者为 ABI
相关工具/布局输入确定的 32 字节身份，必须非零；本组件只做精确匹配，不能用
调用者随手提供的相同字符串替代 SDK 来源认证。源归档签名、SDK 来源、应用
批准、进程权限仍是不同层次。

## 2. ELF 身份载体

采用 ELF64 little-endian x86-64，ELFOSABI 必须为 0，ABI version/padding 为 0。
ELFOSABI 检查本身不是 XOS 身份；身份还须存在且与已批准 generation 完全相等。

身份放在 `PT_NOTE` 中，name 为四字节 `XOS\0`，type 为 `0x584f5301`，
descriptor 为下表的 128 字节。note 只有读取权限，descriptor 必须被同坐标的
只读 `PT_LOAD` 完整覆盖，不能同时被任何可写 LOAD 的虚拟区间覆盖。恰好一个
身份；缺失、重复、未知版本、保留位非零、改变过的内容均拒绝。上限是 128 个
PHDR、8 个 NOTE segment，每个 NOTE segment 不超过 16 KiB；所有偏移和长度
先检查边界。对象角色与 ELF 的 ET_EXEC/ET_DYN、PT_DYNAMIC、PT_INTERP 一起检查。

| 偏移 | 字段 | v1 值/语义 |
|---:|---|---|
| 0 | magic / u64 | `0x31594e44534f5858` |
| 8 | version / u32 | 1；不默许未知次版本 |
| 12 | size / u32 | 128 |
| 16 | role / u32 | 1 bootstrap、2 interpreter、3 main、4 library |
| 20 | machine / u32 | 62 |
| 24 | syscall_abi / u32 | 1 |
| 28 | startup_abi / u32 | 独立动态启动语义版本 1；不是旧 startup_info 的版本号 |
| 32 | libc_abi / u32 | glibc = 1 |
| 36 | thread_abi / u32 | 原生 1:1 = 1 |
| 40 | tls_abi / u32 | AMD64 variant II = 2 |
| 44 | profile / u32 | `xos_glibc_dynamic_v1` = 1 |
| 48 | required_cpu_features / u64 | x86-64 baseline = 1；其他组合当前拒绝 |
| 56 | toolchain_abi / 32 bytes | 精确 SDK ABI 身份 |
| 88 | reserved / 40 bytes | 全零 |

bootstrap 只能是没有 PT_DYNAMIC/PT_INTERP 的 ET_EXEC。其余角色只能是有且
仅有一个 PT_DYNAMIC 的 ET_DYN；main 恰有一个解释器段，其完整字符串包括
终止 NUL 必须等于 `/usr/lib/xos/glibc_dynamic_v1/ld_xos_x86_64.so.1`。
解释器与库不得再声明解释器。旧静态对象不被迫增加本 note；它们继续走旧入口。

这里验证的是身份载体。LOAD 全部几何、实际 DT_NEEDED/SONAME、符号版本、TLS、
重定位、IFUNC、RELRO 和代码最终权限仍须完整启动预检及 rtld 验证，不能据本
函数返回成功就执行对象。测试中的小型链接工件只验证 note 编码和拒绝策略，
不冒称真正 glibc 应用。

## 3. Generation 编码与预算

全部整数按本 profile 的 little-endian 解释。共享头的 `static_assert` 固定
结构大小；无可变长指针、宿主路径、进程句柄或内核 authority。

128 字节 header 按顺序为 magic u64 (`0x314e4547534f5858`)、version u32 (=1)、
总 size u32、非零 generation ID u64、object_count u32、reserved0 u32、SDK
SHA-256 32 字节、toolchain ABI 32 字节、total_file_bytes u64、mapping_budget
u64、startup_budget_ns u64、reserved1 u64。保留字段为零。总 size 必须恰好为
`128 + object_count * 512`，不接受尾随数据。

512 字节 object 按顺序为 file_bytes u64、完整 SHA-256 32 字节、identity
128 字节、bias u64、span u64、needed_count u32、needed 索引 12 字节、SONAME
128 字节、绝对路径 128 字节、reserved 56 字节。字符串必有 NUL，其后全部清零；
路径不允许空分量、`.`、`..`、尾斜杠或控制字符；SONAME 不含斜杠。

| 项目 | 已实施的限制 |
|---|---|
| 对象 | 3–12 个：索引 0 bootstrap、1 interpreter、2 main、后续 library |
| 文件 | 单个最多 16 MiB，精确总字节最多 64 MiB |
| 映射 | bootstrap bias/span 为零，由旧静态装载器处理；其余 bias 在高 arena 内且按 8192 对齐，span 按 4096 对齐，互不重叠；总 span 不超过明示预算，预算最多 128 MiB |
| 期限 | 非零相对启动预算，最多 30 秒；正式启动仍须转换为同一个绝对单调 deadline |
| 依赖 | 保留每对象索引顺序，无重复边、自环、缺对象、bootstrap/main 作为库或循环；所有库必须由 main/解释器可达 |
| 名称 | 无重复路径、完整对象摘要或非空 SONAME；解释器路径只能为上述固定路径 |

这些是准入元数据的硬上限，不是资源预约。真正启动必须继续扣除 inherited FD、
bootstrap、栈、早期 heap、TLS、临时复制与工作内存，检查 files 会话/全局额度，
并与实际 ELF 图交叉核对。manifest 中填写预算不会授予额外资源。

## 4. 受信启动者内的激活状态

`activation_catalog` 是单一受信启动者内、最多四个**预先批准**根的易失状态。
它不暴露服务端 IPC，也没有对调用者身份的猜测或按文件名授予权限。
初始化时复制根 ID/摘要，拒绝重复根和二次初始化；初始 sequence 为 1。

`capture` 返回当前根、索引和 sequence。`activate(index, expected_sequence)`
显式选择已批准且未撤销的根，成功后增加 sequence。重新选择先前根就是离线
显式回滚；失败不会推进 sequence。过时更新返回 `stale`，不静默覆盖其他变更。

切换 active 不改变已经捕获的 generation；加载方可继续在自己的同一 pins 上
完成。但必须在不可逆 commit 前再次 `admit(ticket)`：`revoke` 一经生效，
旧 capture 也会被拒绝，已撤销根不能再次 activate。撤销 active 后不再产生
capture；显式选中另一个批准根才能继续启动。这里不承诺杀死已提交的运行进程。

catalog 没有线程同步；由现有单线程启动者使用。其 ticket 是该启动者内的数据，
不是跨进程 capability，也不能通过接收任意用户提交的 ticket 获得新信任。
跨进程控制、持续 revocation、防重启回滚、发行签名、并发服务协议和进程内
不可逆提交前后语义仍需后续模块，不能把易失 sequence 说成持久防回滚计数器。

## 5. SDK、兼容与错误

native SDK 导出 `xos/dynamic_abi.hpp`、`xos/dynamic.hpp` 和 `libxos_loader.a`
中的实现。代码只使用原生整数、reader 与 SHA-256，不依赖 newlib 私有布局。
本模块没有修改 glibc CRT、私有 D1 handoff 或官方 SHARED 拒绝守卫。

所有函数用 `dynamic::error` 报告阶段：I/O、边界、header、identity、角色、
解释器、可写身份、摘要、SDK、预算、路径、冲突、依赖/循环、状态、撤销、过时更新。
不把错误转换成成功或省略未读取对象。退回旧 SDK 时，旧入口继续拒绝动态 ELF；
新头/API 需要匹配 loader archive，不能只复制头到冻结 SDK。

验收入口是 `tests/dynamic_admission_guest.py`：宿主与真实客体运行同一组负例，
客体从 matching SDK archive 链接实现，并从实际 readonly file pin 验证普通
GCC 生成的 note 工件与文件游标不变，最后核对进程/页/句柄资源基线。具体计数、
构建身份和已知未验范围以对应 work_log 与 report 为准。
