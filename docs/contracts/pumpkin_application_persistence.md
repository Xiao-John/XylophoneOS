# Pumpkin 应用数据与安装事务

本契约定义 `--pumpkin-anchored-probe --pumpkin-provisioning-store` 明确选择的
原生 provisioning profile。它复用 Pumpkin 账户核心、Files 独占私有区租约、
`snapshot_publication` 和独立 generation authority；不读取 FAT 上的文件来
自行授予应用权限或批准安装根。旧账户、named resource 和旧私有区 profile
的磁盘与 IPC 格式保持原样。

## 发布单元与范围

`PUMPROV1` 完整快照包含原有最多 64 个账户、8 个只增不复用的应用记录、
最多 4 个批准根的 catalog，以及一个仓库防回退 checkpoint。每个应用具有
稳定编号、账户 owner、授权 epoch、enabled/rights、名称、独立凭据 verifier、
数据 revision、最多 512 字节的数据和安装 generation/manifest SHA-256 receipt。
这些是有界的应用状态与安装元数据；本 profile 不提供任意大小的 POSIX 文件系统。
应用安装 receipt 本身没有批准新 generation 的权限。

外层固定开销为 6192 字节，完整快照为 `6272 + 68 * account_count` 字节，
最大 10624 字节。所有可变长度的未用尾部、空记录和保留字段均须为零，账户
快照和外层快照分别验证完整性。应用编号、数据 revision、授权 epoch、catalog
epoch 和外层 revision 溢出时返回 exhausted，不能绕回或复用旧编号。

Files 私有区 descriptor v2 明确指定两个 32 扇区槽，每槽 16384 字节；
旧 v1 的两个 9 扇区槽没有迁移或自动探测。公有 FAT 容量仍严格止于 descriptor
之前。对应私有租约 protocol v2 使用有界 2304 字节 chunk；末 chunk 使用实际
剩余长度，传输未用尾部清零。账号 profile 的独立 authority record tag 为
`PUMGEN\0\3`，旧 tags 不能用于新快照。

## 原子提交与恢复

单一 writer 持有真实 Files 独占租约。任何账户、应用数据、应用授权或 catalog
变更都编码为下一份完整快照：

1. 比较当前受保护 generation 的完整记录，并验证其精确选中槽。
2. 写另一个槽，完成 Files sync 和完整 readback。
3. 由独立 authority 对旧完整记录进行 CAS，发布新 revision、长度及 checksum。

只有第 3 步确认 committed 后，服务才更新可见内存状态。确定未发布时返回
io_error 并继续使用旧状态。冲突或 outcome_unknown 使 store 和账户核心停止，
只允许有界地排空已排队的最终答复；后续请求不执行、不自动重试。

重启只读取 authority 选中 revision 对应的槽，并核对 realm、长度和 checksum。
它不扫描另一个槽来猜测最新版，也不会为了可用性自行恢复一个旧授权。
独立 authority 选中新根但所需磁盘字节缺失时，启动明确失败。

真实 guest 验收在 Files 完成写入和 readback 后，于独立 authority 的 CAS/ACK
边界注入 rejected CAS、committed unknown、uncommitted unknown，随后使用新的
虚拟机进程冷启动，检查旧/新数据与安装 receipt 必须成对恢复。此证据没有证明
任意时刻物理断电、真实存储控制器写缓存或整台宿主回滚；正常关机和 QEMU
进程结束不能替代这些资格。

## 账户与逐应用 authority

应用凭据由服务的 kernel entropy 源生成，服务只持久保存带 realm、应用编号和
独立 domain 的 SHA-256 verifier。原始凭据只通过真实 registrar 的认证 endpoint
返回一次。普通应用操作同时要求：

- 当前连接自己的有效 Pumpkin 账户 session；
- 该账户是服务端记录的应用 owner，且账户仍 enabled；
- 与该应用匹配的独立凭据、当前 application authorization epoch 及所需 rights。

请求中的应用编号只是选择器。其他应用的凭据、伪造 owner、其他连接的 session、
旧 epoch 都不能授予权限。读操作不会返回 verifier。应用数据写入使用 expected
data revision，安装 receipt 只能引用当前 catalog 中未撤销的批准根。

只有真实 registrar 可以创建或撤销应用、查看安装记录和执行应用安装/迁移事务。
普通客户端不能通过自报 PID、角色、owner 或“已验证”布尔值取得这些权限。
账户撤销和应用撤销写入同一受保护发布单元；撤销提交后，新操作检查当前状态，
包括已经建立的其他连接。已经通过授权、进入单一 owner loop 的一次操作可以
完成。此处不承诺立即终止正在计算的程序；动态后代的启动撤销由 P1-C 的 live
admission 契约另行完成。

## Catalog 与发行控制器接口

`checkpoint` 返回当前完整 catalog/checkpoint 和
`{revision, authorization_epoch, catalog_epoch}`。`stage_catalog(expected, candidate)`
在一个 CAS 中发布候选 catalog.active 与防回退 checkpoint，不能先激活后补记
checkpoint。调用方必须先完成包闭包、全部对象字节和 manifest 的验证；本存储层
不把 candidate 的自报 digest 当作签名证明。

catalog 仅允许追加批准根，已有 root 的编号、digest 和 manifest 路径不能修改；
历史 revoked 位不能清除。仓库 ID、SDK digest 在同一 store 内固定，key epoch
不得下降，sequence 严格增加，trusted Unix time 不得下降。时间和签名/密钥策略
由发行控制器检查，不接受普通 CLI 指定的“可信时间”。达到 4 个根时需要明确的
受权迁移方案，不能偷偷覆盖旧条目来清除撤销历史。

`delegate_publisher` 只在真实启动父 registrar 的 endpoint 上接受。父级必须以
真实 spawn 得到的 child 身份核对其 startup 通道，再提交 daemon-side pair。
daemon 通过 kernel query-peer 核对 pair 的真实 peer，并与已接纳 session 的
两个 endpoint 完全匹配，才赋予 catalog publisher 角色。该角色仅可查询、提交
catalog 和进行 generation admission 检查，没有账户、应用数据、再次委派或
撤销其他应用的权限。连接断开、进程死亡、exec 或 endpoint 失效会结束角色；
fork 不继承有效 endpoint，需要受控 bootstrap 重新建立。

所有 provisioning 请求使用独立 PPR1/version 1 帧，保留原账户协议。两种帧共享
同一连接的严格递增 sequence、有限 deadline 和 bounded reply drain。格式错误、
重放和超时关闭连接；发送后的未知结果不重放。公有 syscall ABI 没有变化。

## 证据

Host 测试为 `tests/pumpkin_provisioning_host.py`，直接编译生产 store、codec、
RPC 和账户核心，覆盖 torn staging、CAS 四种结果、旧磁盘拒绝、满 64 账户、
跨应用凭据拒绝、限权 publisher 和持久撤销。Guest 测试为
`tests/pumpkin_provisioning_guest.py`，通过真实 private Files lease 和 daemon IPC
执行数据/安装事务，按各故障结果在新 VM 中检查恢复。对应 PR 的 work log 和
平铺 evidence manifest 记录实际工具版本、产物和执行结果。
