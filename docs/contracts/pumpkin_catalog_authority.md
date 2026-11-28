# Pumpkin 持久 catalog authority

本契约在 [应用数据与安装事务](pumpkin_application_persistence.md) 的同一受保护
发布单元上保存批准根、active、撤销位图和仓库 checkpoint，并把当前授权接入
[公共 GNU 启动闭包](public_dynamic_runtime_v1.md)。所有构建和执行结论必须引用
其实际输入摘要；源码接口存在不代表新 GNU 产物已经通过客体验收。

## 持久选择与撤销

每个 installation 最多保存四个批准根，根由 generation ID、完整 manifest
SHA-256 和规范绝对路径组成。SDK digest、仓库 ID、既有根与历史 revoked 位
沿用 P1-E 的约束。相邻 JSON、普通 Files 路径、客户端自报的 PID 或验证布尔值
不产生批准权。

stage_catalog(expected, candidate) 在一次 protected CAS 中发布完整 catalog
和单调仓库 checkpoint。签名、可信密钥、时间、包依赖和全部对象验证由受限发行
控制器先完成。catalog store 本身不把 candidate 摘要当作签名证明。

registrar 的 activate_generation(expected, index) 只能选择已保存且未撤销的根；
它增加 catalog epoch 并在同一持久单元中提交 active，不更改发行 sequence。
revoke_generation 增加 catalog epoch 和 authorization epoch，并永久设置该根
的 revoked 位。撤销 active 时选择第一个仍获批准的根；全部撤销时保留完整撤销
状态，启动查询拒绝执行。最后一个根也可以被撤销，不能为了保留一个可运行根
而拒绝安全管理员的撤销请求。

expected 包括 revision、authorization_epoch、catalog_epoch。失败的已知 CAS
保留旧状态；未知结果停止 store 和 daemon，不重放操作。下次启动必须依据独立
authority 的完整 revision/length/checksum 选择同一旧或新发布单元。旧磁盘与
新 authority 不匹配时拒绝启动，不能把它当作空账户或新安装重新初始化。

## 受限发行查询

PPR1/version 1 的 request/reply 仍为 1592/1560 字节，既有操作 1–11 不变。

| 操作 | 编号 | 准入 |
|---|---:|---|
| publisher_checkpoint | 12 | 当前真实 registrar 或 catalog publisher 连接 |
| activate_generation | 13 | 当前真实 registrar 连接 |

普通公开 checkpoint 可用于读状态，不能证明发布权限。发行控制器必须先通过
12，才开始任何 staging 写入。该角色由 daemon 已验证的 endpoint pair 和真实
kernel peer 决定；请求中没有授予自己 publisher 角色的字段。12 不写持久状态，
不增加 revision。13 使用 index 作为选择器，不接纳新根。catalog publisher
不能使用 13 改变管理员选择，也不能创建账户、应用或再次委派。

C foundation 同时交付供 D 使用的 src/user/include/xos/distribution_startup.hpp：
固定 XYPMSUP1 magic、96 字节 publisher_startup 和 offer/broker/connected/delegated
四阶段枚举。它只描述启动消息，不授予角色；调用方必须认证真实 kernel parent、
broker 与实际已接纳 session，再通过 PPR12。D 的发行实现与实际验收另行交付。
先纳入此冻结轻头可使共享 runtime、native SDK 的全部源输入在 C PR 中完整重现；
不能为省略一个尚未合并的头而删改 native_inputs 清单。

## PCQ1 只读启动查询

src/shared/include/xos/catalog_abi.hpp 定义独立 ABI：

| 记录 | 版本/大小 | 含义 |
|---|---|---|
| authority binding | version 1 / 64 字节 | daemon PID、16 字节 realm、32 字节 service 名 |
| PCQ1 request | version 1 / 40 字节 | magic、sequence、绝对期限、realm |
| PCQ1 reply | version 1 / 784 字节 | 状态、revision、authorization epoch、realm、728 字节 catalog |

受信控制器以其实际启动并认证的 daemon 身份构造 binding。读取端通过现有 named
IPC 建立新连接，查询两端 kernel peer，并核对实际 daemon、realm、协议版本、
sequence、保留字段、revision 和 catalog。服务器只读当前 owner loop 的已确认
持久状态，不把 PCQ1 查询当作授权委派。

每次读取使用新连接，最后关闭；fork 后不能复用父进程 endpoint。查询沿用一次
启动的有限绝对期限，单次交换最多五秒。发送后不重放；连接、响应、daemon
可用性或时间不能确认时拒绝启动。服务停止和错误 peer 均不能降级到本地政策。
持久 provider 的可用性由 daemon 实际 backing 操作确认；此协议不承诺在尚未
进行任何 backing 访问时即时察觉宿主 provider 停止。

## Capsule v3 与后代准入

动态只读 capsule 显式升级为 **3**，新增完整 authority binding；不复用原
reserved 字段。固定地址、160 字节 prefix 和原保留字段约束不变。构建 native
NOTE 的 ABI 身份使用 xos-glibc-dynamic-capsule-v3 domain，并绑定 catalog、
动态启动和动态对象 ABI 头。SDK header、archive、bootstrap、共享 libc/rtld
必须由同一源输入重建；旧 v2 动态组合不能被标为已验证的 v3 组合。

dynamic::install_anchored(binding, deadline) 读取当前持久 catalog，再调用现有
完整 closure 验证与公共 install。普通易失 install(policy, deadline) 仍可使用
空 authority binding；它没有跨进程 live revocation 资格。

子映像继承只读 binding，并在 startup 恢复该进程自己的 generation artifact。
每次启动或 exec 准入同时要求以下三个身份仍获当前 authority 批准：

1. 控制器进程自己的 capsule artifact。
2. 当前被替换的 artifact；新子进程的 current 可以为空。
3. 请求启动的目标 artifact；目标不能为空。

自身身份检查不能只看 current：新建子进程的 current 为空，一个已撤销父
进程也不能通过选择另一个仍获批准的根绕过撤销。原生受信控制器没有 GNU
artifact 时可有空 owner；它仍需核对当前和目标。

fork 保留独立政策及自身身份，但每次 admission 重新连接 authority；同 PID exec
从新只读 capsule 恢复绑定与新 artifact。后代不能因持有旧的本地 policy
snapshot 而绕过当前撤销。已经获准的 grant-to-commit 事务可以完成，不承诺即时
终止计算、取消已接受的所有事务或广播停掉进程树。撤销以明确的 root 为单位；
先前已合法转换到另一根的进程不自动继承被撤销旧根的永久污点，必要时管理员
应明确撤销相关根。

这是受信 SDK 启动控制路径的 authority 校验，不是新的全局内核代码执行策略。
它不把任意手写 syscall、恶意修改自己数据段的程序或未使用该控制路径的静态
程序宣称为已被 kernel 强制纳入 catalog。

## 独立 Linux provider v2

旧 xos-pumpkin-local-provider-v1 字段与账户/named 格式保持不变。显式
xos-pumpkin-local-provider-v2 额外要求 provisioning: true 且
named_resources: false，将 mark decode、provider client 和 authority 构造全部
绑定到 16 KiB provisioning profile/tag 3。不会根据磁盘内容自动升级 v1。
原 operator login 入口拒绝该 v2 profile，避免旧账户布局误读应用事务。

v2 延续独立的非 root operator/provider UID、可信 profile digest、真实 Linux
SO_PEERCRED、provider 私有 authority 根和完整 CAS。部署 realm 必须为精确
16 字节，非零且不同于 developer realm。错误 UID、错误 realm、格式不匹配或
旧 authority record 均拒绝。--pumpkin-deployment-realm 可显式用于 provisioning
构建；独立部署必须绑定对应系统 manifest。

## 验收边界

Host authority 测试直接编译生产读取和 admission 代码，覆盖 owner/target、
错误两端 peer、realm/version/sequence、不可用和超时；其 IPC 是模型，不能
替代实际 kernel peer 的证据。生产 store 测试另覆盖权限、CAS、active 撤销和
全部撤销后重建。

tests/pumpkin_catalog_guest.py 通过真实 private Files 和 daemon IPC 运行两个
GNU generation：注入拒绝、已提交但答复未知和未提交且答复未知，再在新 VM
中实际启动被选中的旧或新 ELF；另用真正的 reexec、fork 子进程和孙进程检查
撤销前可启动、撤销后拒绝，以及 daemon 不可用时拒绝。显式原生 owner 种子
测试与 GNU 后代测试分别记录，不能互相替代。

该测试 profile 以现有 sys84 named pair 承载 supervisor/proxy 控制消息；双方
核对实际 kernel peer，并完成精确 PPC1 HELLO/ACK。daemon/proxy backing
仍使用 sys81，主管在启动前枚举并要求自己持有两个 sys81 endpoint，给真实
动态 READY/ACK 留出现有配额。默认 E/P2 profile 和内核容量不变。串口帧中
100–179 为启动 stage/error 的失败诊断，只有 finish 1 可判为通过。

独立 provider gate 在真实 Linux VM 内使用实际 UID 1001/1002/1003；它核对
peer、私有记录权限、CAS、格式拒绝和 provider 冷重启。它不证明用户物理宿主
已部署。XOS guest 的 developer authority、Linux UID isolation、物理硬件和
任意断电是不同资格。普通 sync/reboot、停止 QEMU、杀死 host 进程均不能
冒称任意掉电验证。
