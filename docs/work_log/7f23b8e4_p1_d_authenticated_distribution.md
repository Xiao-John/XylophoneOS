# 7f23b8e4 P1-D 认证发行与批准代际安装

## 完成结果

P1-D 已在 SDK 开发环境中完成实现和真实 guest 验收：独立编译的官方信任根、
EVP Ed25519 签名验证、原生时钟有效期检查、受保护 checkpoint 防回退、有界
P3 依赖解析、完整 generation/ELF 校验，以及经真实 publisher 委派的不可变
staging 和单次 catalog/checkpoint CAS。正式交付安装器实际运行，不以 host
工具或同包携带的公钥替代认证。

最终证据入口是 `docs/reports/p1d_authenticated_distribution/qualification.json`；
同目录 `README.md` 说明来源绑定、可重放字节和资格边界，`manifest.json`
登记每个证据文件的精确 SHA-256 与长度。

| 实际验收 | 结果 |
| --- | --- |
| production verifier，真实 EVP ordinary | 30/30 |
| 同一 verifier，ASan/UBSan | 30/30 |
| 既有 P3 repository 回归 | 50/50 |
| package cache 回归 | `XYPm_HOST_CACHE_OK` |
| 独立测试仓库，五次 fresh guest boot | 5/5 |
| 官方仓库，公开交付安装器，三次 fresh guest boot | 3/3 |

八次 guest boot 合计运行 15 次实际安装器：4 次确认安装、10 次预期拒绝、
1 次暂存中断；每轮最终都启动实际 GNU libc 应用，共 8 次成功执行。原始
测试报告 SHA-256 为
`7a51d09b84295ae5c09d6ee2bea5e34c197487a1c3d6948d4b48f53bbe17b9a8`，
原始正式报告为
`473ddf90189da7eac691003f5d69d737d533c7845541dee287ca9a3df1b23c65`。
这些是环境恢复后重新执行的结果。

## 实际发布、错误和中断路径

测试场景 32 通过真实 registrar 委派、PPR12 权限证明、签名与全闭包验证，
安装 generation 1101 / sequence 1，在一个持久发布单元内将 checkpoint 和
catalog 提交到 revision 2，完成 GNU 应用的 READY/ACK 和退出 0。

场景 33 分别拒绝八种输入：未获 daemon 委派但收到父 ACK、metadata 字节被
改动、已过期签名、另一把私钥的签名、依赖环、依赖版本冲突、包缺失、包中
对象字节被改动。逐例检查实际诊断和 exit 3；完整受保护状态保持不变，
随后旧 GNU 应用仍正常运行。

场景 34 在新对象首次 sync 后中断实际安装器，退出 70。已有目录和同字节
runtime 对象已验证复用；部分新对象没有批准根，旧 catalog 和旧应用保持。
场景 35 重新验证并安全复用该不可变对象，安装 generation 1102 / sequence 2，
一次 CAS 提交 revision 3，运行新应用。场景 36 拒绝旧签名版本，仍运行
revision 2 的 GNU 应用，受保护状态保持 revision 3。

正式仓库再用实际发布者签名和公开交付安装器独立完成 32、35、36 三轮。
正式公钥是独立配置的 `xos.official` epoch 1，公钥 SHA-256
`b0f1a4b64fc9e81dcf6a104d67ca7f3dd662ea993c72d6570c182ec76d316bd6`。
两个 metadata 摘要分别为
`bc9a62f84dd1a54f5f536b353f788fbd0f663ee0eb4cc8a546287279b9780b68`、
`ff73a37608363d8c6e054252733e938216d8a019e96705938b88964b0aad6443`。
它们的有效区间是 2026-11-28 11:54:31 至 2026-11-29 11:55:31 UTC；过期
后的实际安装应拒绝。上海时区对应 11 月 28 日 19:54:31 至 11 月 29 日
19:55:31；到期的是这两份签名仓库 metadata，SDK 本身不会因此过期。
之后的官方发行必须使用新的递增 sequence，不能给
已发布 sequence 重新签不同 metadata。发布私钥不进入源码、包、镜像或证据。

## SDK、运行库与公开产物

安装器和应用绑定同一新 glibc C/C++ SDK/profile，profile id 为
`xos-x86_64-glibc-p1-20261128-v1`。其 SDK manifest 摘要为
`0c876bac53354501159df75813711002c41baede650f1878116bb64a80a8190b`，
tree 为 `ce808de26f1ede38a543c94bba5d5a5592606c71305267854cb57ea519429254`。
目标 libcrypto.a 摘要为
`a3dc4ba4d2da1f5c6b0f940c56ac901a6eb8c07bfdf03599802216b9bc1b5d96`；
静态 SDK 不因此被误称为已包含动态 GNU fork 支持。

C/D 共用唯一 shared GNU runtime，原始 manifest 摘要
`a7a6360491bb8ebe13b85aab61be7d61d0cd26137d1f02f433d7ca908e8bd0dc`，
native ABI `9dafe8ee0e45fbc1ccb00ee2362d1be5db38584553efcb8ae7a50d699cd4c849`。
最终系统的 154 项 native、14 项 recipe、303 项 port 输入逐 SHA 全部一致；
9 个最终 runtime 产物也逐一匹配。native SDK v1 用于构建应用，最终系统 v3
仅改变专用 fixture 和租约 profile，完整系统 build id 仍分别记录，未伪称
两套系统字节相同。供 D 使用的 96-byte publisher bootstrap 头先纳入 C
foundation，避免 C 的独立源闭包依赖尚未发布的 D 文件。

最终系统 build id `a4ccfa274f90578f`，原始 manifest 摘要
`dddd5ac5252c314543005b0a1f020f7385b9d0b1de5889b912cc58a4295a9fc5`。
专用 supervisor 在构建并生成 manifest 前显式 strip-all；entry、PT_LOAD
属性和每段完整映射字节严格相同，原 ELF 保留。

原官方安装器的调试段含 SDK 安装路径，公开路径检查明确拒绝该包。新增
显式 `build_xypm.py --public-artifact` 在打包前 strip-debug，并保存原 ELF、
原回执、工具和 recipe 摘要。GNU ELF 首段包含文件头，剥离会更新
`e_shoff`、`e_shnum`、`e_shstrndx`；最终证明检查完整程序头、入口、映射属性
和除这三个节表元字段外的所有映射字节相同，并同时登记原始逐段摘要。
不能把这描述为全部 PT_LOAD 原始摘要相同。最初严格逐段 guard 的拒绝和
后续分析也保留。最终 XPK 摘要
`6e2be19d6bb1cc01c680f12a86ffbd1bd3720199c1eb69e01740d9957aa0d033`，
最终 ELF 摘要
`017052e197a6b803c72656b1a1adc91ec2c650d1410204f694dc5d48bb27a274`。
正式三轮运行的正是这份交付字节。

## 保留的失败与修复依据

本组在 `6332527ab64e92371266363f41f3247717a3cac8`（B/E 已合并）上重建。
执行环境曾断连并回退，尚未发布的旧本地工作和日志丢失；没有重造旧报告。
`recovery_checkpoint.json` 保留原始 `WIP_NOT_QUALIFIED` 历史状态，独立的
最终 qualification 依据新实际运行将它替代，不修改旧失败为成功。

恢复后的首轮 CAS 失败、日志关闭 deadline fixture 失败、死通道诊断，以及
没有获得 console 到期输出的租约诊断全部保留。实际死通道在 guest 单调
时钟 33.5 秒观察到 send、peer query 和 try-send 均为 -1，authority 仍只有
初始化 revision 1。源码给出的 30 秒 Files backing 到期撤销、backing.live
失效及 daemon 关闭 PPR 通道，与观察吻合；这里明确是源码和时间的因果
推断。COM1 已交给独占 proxy，未观察到直接到期 console trace，不能声称
取得了那项输出。

最终构建显式选择 C 的 `launch_acceptance` backing profile，时长 300 秒，
profile 和 duration 计入系统身份。默认 30 秒、每次 RPC 5 秒、安装器总
staging 120 秒均保持原边界。修复后同一 runtime 实际跨过原 30 秒界限并
确认 CAS；这提供比较证据，不靠放宽单次在途请求或接受失效通道。

fixture 另消除了无谓持有的旧 supervisor/proxy sys81 pair：控制消息经
已有的 authenticated sys84 HELLO/ACK，生产 daemon/proxy sys81 pair 和
内核四 endpoint 界限不变。sys81 枚举只列参与收发的端点，不列 supervisor
仅为 owner 的 pair；fixture 保留两次成功创建的句柄，并断言参与枚举为 0，
最终仍需通过真实 loader READY/ACK。

## 权限与证据边界

签名成功不能授予执行、网络、账户或发布权。不可变公共 FAT 文件与受保护
catalog CAS 分别校验；写入前必须收到实际 daemon 的 publisher 查询成功。
没有新 syscall、没有声称存在新的 scoped FAT grant，也未复用 P2 全盘
maintenance。已有对象只按同一打开句柄、pin 和完整摘要核验同字节复用。

本组 guest 使用显式 COM1 developer authority；独立 UID production provider
的实际资格在 C 单独登记。D 中断门位于不可变 staging；未知 CAS 的实现
采取 quarantine 且不重试，其故障资格由 C/E 的持久事务矩阵分别登记。
不据普通 sync 或进程中断声称任意物理掉电安全，也不把本组的成功延伸到
独立 P1-K2 所属的 shared GNU fork，后者仍为明确 ENOSYS。

公开回执是注明原始摘要的路径投影，原始回执不变。二进制 serial 使用
可逆 base64，同时保留原字节长度和原 SHA-256；外层 JSON 的摘要由证据
manifest 单独登记。只清理完成的可重建解包源码/诊断对象，并对保留的
ELF、ISO、SDK archive、manifest 和日志做前后摘要检查；失败磁盘经完整
解压摘要验证后无损压缩，具体回执均在证据目录。
