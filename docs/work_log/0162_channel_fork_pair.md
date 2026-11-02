# fork 子进程的通道对派生

依据 0160 的会话事务勘查，为通用 sys81 增加试行 `fork_pair`：仅已有双向通道
参与者可为自身待提交的直接 fork 子进程派生独立端点，沿用原对端、控制者和容量。
内核检查端点方向、身份、空槽、子进程状态、重复和总额度，双端点先检查资源再
分配；子进程 abort/退出会按既有通道清理规则撤销。完整边界见通道契约。

新增探针覆盖未提交子代的派生、原申请者不能冒用子端、重复申请失败、对端枚举到
独立身份，以及 abort 后对端不再枚举到派生端点。常规构建与探针交叉编译已通过；
提交 `d805c9d00b355c06f59c1285b43287ff67b90a89` 后重建并运行客体，结果为
`passed_subset`，包含上述身份、重复和 abort 检查。build ID `969bf64ef98004e9`，
系统 manifest SHA-256 `ede34a5df46ade118f24fd4f11d294129c0ea679f5c4e28f0ccf4c25ff4516b0`，
镜像 SHA-256 `071e0485e685df99963523fb1f07de11dca28a7fab0f90b617213d888a824d2b`，
SDK 树 SHA-256 `d17ac7ba730084c1b1c46d49c0bb3cbeb1a1d84cfed39f9c983554a9f85b9aa0`，
串口 SHA-256 `ca0a367b8f781c5b7b22562d7f11ad18ffc19b230e2d0c72d0f060d6d1837693`；
报告位于 `build/w1_fork_pair_run_d805c9d/`。

此机制不实现对端同意、终端服务多路仲裁、libc fork 交接或 W1/W2 资格；仍需
拒绝矩阵、fork commit、退出/故障及资源压力验证。

提交 `8a8cff2dcd6dac01499c5a105e0c96da921cf341` 后重建，客体 `passed_subset`，
增加验证反向端点、非待提交子进程、重复源句柄、非零输出字段及无效句柄被拒绝。
build ID `8195e116df8c760b`，系统 manifest SHA-256
`2c2a5380005d4acb41fb5afc521bc3434283ea301f38fc5d9dfbed18fad1c6c8`，镜像
SHA-256 `c29958901f7bf55b83295ad509a7dca54ba32fc3ed924baab2188c707dbfaeaa`，
SDK 树 SHA-256 `98b404991f20dab2cf5d7336a73228f47e9e04262f7813c056df9d1c1ad8134b`，
串口 SHA-256 `9f10ce32d02b1d91068fd8a47a9c3e0f3584748eddf7b57c97118b9d4fb03f55`；
报告位于 `build/w1_fork_denial_run_8a8cff2/`。这些断言不构成完整拒绝矩阵。

提交 `349bd8ee2f34afe1a0296219952e510fad2c8256` 后重建并运行真实提交路径
探针：对端核对新端点，父进程完成 files 会话克隆并提交 fork，子进程以自身身份
枚举通道并与对端双向通信，退出后对端确认端点消失，结果 `passed_subset`。
build ID `1843f6889070bf0d`，系统 manifest SHA-256
`ae8d3b3ea12abf76c2fa00ea878ff6b7a544dbff4f46f662f272a013145a7b8d`，镜像 SHA-256
`e60332550a5b5c89f9323990dc2b21cafe30115545bfbbfde0dd19ad874e53bd`，SDK 树
SHA-256 `fb780555ace2028e45ce51f60320bc5157437a4d11e8f1665547fd410543e975`，
串口 SHA-256 `4d7e23346fbc242d7c4e09d446a7dbf9254611d7ec0485945c163b02f308b3c2`。
报告位于 `build/w1_fork_commit_run_349bd8e/`。这不验证终端服务登记或完整进程交互。

终端服务将唯一应用的接收等待改用 `wait_many`，对伪唤醒重新检查；这是扩展
等待集合的准备，仍只有一个应用会话。提交 `d3e882baf18020856d2acd760b8dd9388cd771a6`
后重建系统及组合 SDK，在正常 Xsh 客体中既有宽字符、重入、locale、应用故障、
服务重启和资源基线探针 `passed_probe`，exec 模式、别名和 CLOEXEC 探针
`passed_subset`。build ID `8e3e087444bcacca`，镜像 SHA-256
`86caa357975e192018d8f9ee44ddd15e808b1677748fc86202a73c167b8d80f7`，组合 SDK 树
SHA-256 `aab7b56459094f2f95752d46a17ee9f2deb42307692e7a4883b3f0b31c3ca1f9`，
ncurses 客体串口 SHA-256 `36047062be63edf5d10b5599af0aa90242009c1c00012c279d2d750f7192a017`，
exec 串口 SHA-256 `40010b2b8e7ae840065cd9eee8f94dd5e2dca700e5a487f8f6dbb59f65c5e1e6`。
报告分别位于 `build/w1_terminal_many_d3e882b/` 和 `build/w1_terminal_many_run_d3e882b/`。
这些是单应用受限回归，不证明多会话或 W1/W2 完整资格。
