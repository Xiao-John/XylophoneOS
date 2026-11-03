# 单线程 libc 的终端 fork 交接

单线程 libc 检查是否持有终端描述符；若持有，在 fork prepare 后为未运行子进程
派生通道对、通过父会话登记，再克隆 files 会话并 commit。任一前置失败都 abort
子进程；登记传输错误可能使旧会话结果未知。子进程从内核枚举到的独立通道重新
绑定终端客户端，沿用已复制的描述符表及别名；服务若在 commit 后失效，fork 仍
返回成功，后续终端操作报告错误。多线程 profile 仍拒绝 fork/exec。

普通 Xsh 的 `tty-run` 授予现有一级进程创建权限以允许该事务；这一权限同时允许
现有受限 spawn，fork 深度、全局进程数及终端会话上限仍分别生效，非完整作业控制。
专用探针与正常 Xsh 探针分别增加 libc fork、描述符别名、共享模式和子进程写入；
提交 `6b880b7e695eefc8172e3ee63a45732b3a0f1196` 后重建两种系统：正常 Xsh 的
exec、fork 描述符别名、共享模式及子进程退出探针 `passed_subset`，build ID
`2b20caeaf078d3fe`，镜像 SHA-256
`33d1f6ef5a065bbdd69822f265c7a40174f9825b3934d86d71e42f553a8ddcfd`，SDK 树 SHA-256
`a1d7f11da45f847e760633e920cc810fdf07cec80057cbbde78f2c667b3b5061`，串口 SHA-256
`73fe1efcb789b1a0b73f6f8d73fd6b8c8dfea90cb05e6f3743f6b21ac7828488`，报告位于
`build/w1_libc_fork_normal_run_6b880b7/`。

专用 supervisor 的原有设备交接及 libc fork 别名写入探针通过，build ID
`1ae1259d3e03b9fa`，系统 manifest SHA-256
`01f1ca7e2569e1737ea076dbbdf2cfa78392cf518038ae3a82a9dc644dee66d5`，镜像 SHA-256
`e0093afec1f65320e55d1f0c303385f0c10b631d8a17aa77476255203d1a7b42`，串口 SHA-256
`79739289379ec6d056b0bf51f30ac1806b8a326cbeba77e595f2f13c73387331`，报告位于
`build/w1_libc_fork_special_6b880b7/`。失败回滚、权限、并发和资源压力仍需单独覆盖，
不能把一次成功路径作为完整 W1/W2 资格。

增加容量与回收探针：两个子进程以管道同步保持会话，第三次 fork 应因容量不足
失败，父进程终端仍可查询；释放并回收子进程后再 fork 应成功。提交
`179c66826614ba7e12cbdcbd9aa0a9543c9d82d8` 后，正常 Xsh 客体该子集通过；
build ID `d5fdd59f2d2bec4b`，系统 manifest SHA-256
`3598709c8f9b882f31561d2f835ba45cf9ab70d9f985b7f073456ee3b1b3ce6f`，SDK 树 SHA-256
`de65f9e1f738b0cc168c961862a6d53fbe783b5dc622e9d8cbcbb4c269e050da`，串口 SHA-256
`0aaf26b1c760aac4a3627fdd0a65cd1f3b4fb77f8b6b17030ca0d730ac3ed220`，报告位于
`build/w1_fork_cap_run_179c668/`。此结果未区分哪个资源先耗尽。

提交 `40ed6684c96315e6e064795e99fb869178df4dd8` 后重建，新增断言在两个子会话
仍存活时先单独 prepare 成功，随后通道对派生明确返回资源不足且输出保持零，再 abort；
其后的 libc fork 失败、父会话可用及回收后重新 fork 均通过。结果 `passed_subset`，
build ID `c21a53fe45667563`，系统 manifest SHA-256
`5fd00b882ac021099b88272056b20a3212b34bc346797e48a28f8355c22d7812`，镜像 SHA-256
`d7a1c460833596c5464feebcd583edda58e263fc03b0f38071705941c99a4c3c`，SDK 树 SHA-256
`1ad9c3c62992ff537202f7df5c60d1854e36232b4f06d4fd2e8ac54401040eab`，串口 SHA-256
`f3db96367f85f429214b09d60089297cd3b592b210664228a7b4c0309283a085`；报告位于
`build/w1_fork_quota_run_40ed668/`。本项不证明其他故障路径或完整资源压力。

探针进一步比较 prepare/abort 和 libc fork 失败前后的进程数、线程数、保留与结果数、
空闲页及当前进程用户页和内核栈页；不比较会随调度变化的等待线程数，也不将这些
计数冒充端点池统计。提交 `a06472a1a36cf2d24a5db1db864c2e69ea445bcd` 后重建，
客体结果 `passed_subset`：两次失败前后上述计数一致，释放子进程后可再次 fork。
build ID `3c9cb4b19247dc93`，系统 manifest SHA-256
`aef701e1bfce4b6dc9f38fcfd078d8ff9d6625574741147f2f10bfef88961d71`，镜像 SHA-256
`477793e9936d4933448c6783b947c40d2fe6c7617718c13d450bb278c703cc03`，SDK 树 SHA-256
`11c4484c68a50b4f4b4ca9b1d6696c8cb5e0d8caf3db36c4d56d6931d0e7a467`，串口 SHA-256
`42ee31b5f1c519b611aac53c614715a5644be076098329e51c9085bb12d286e0`；报告位于
`build/w1_fork_rollback_run_a06472a/`。其他错误位置、并发和故障仍须验证。

新增多会话中断探针：父进程在原始模式阻塞读取，子进程以管道通知就绪并延时后
发起终端写入；父读取应返回 EINTR，子写入与退出完成后父会话仍可使用。延时只用于
建立该受控测试顺序，不作为公平性或时间上界证明。提交
`362454dc462344220a495504192d27e2dc80f2b9` 后客体 `passed_subset`，build ID
`3441f661e794b378`，系统 manifest SHA-256
`e1df0fce9a5c03b531011ec0984d13a457b0f2929c249c81f31d102aefa2d912`，SDK 树 SHA-256
`68a9c8dddc26328cd3d5230634bc0ae2caa78d26602e697fd057968b005d6245`，串口 SHA-256
`282b030051f21205cf62a6017f70918fd41a7d4b399c848aa42ceaa8d20cc706`；报告位于
`build/w1_fork_interrupt_run_362454d/`。提交
`c1bed30735b526b989f095edd8c3612163d8ab30` 后重建，子进程不写入而直接退出时，
端点关闭唤醒父读取并返回 EINTR 的客体子集也通过；build ID `aece30c8b29acc0f`，
系统 manifest SHA-256 `478fa5e45a95d509b9bb7974f5c0ede22481d1b53588c9b86f601028c55afd51`，
镜像 SHA-256 `d60be1c3770a0f7f652a3bfeca8c69cb9a6cc3188dc53bba5539b75f197f6e29`，
SDK 树 SHA-256 `e8520c6a4628e3ecdce0388e0e476c419bbce8d1e08996a5272e8e9fe29edf38`，
串口 SHA-256 `fd2b9e7f16e5fa91521a069ca5ac7c092d476b7052a6d59887d5c973ef91d613`；
报告位于 `build/w1_fork_close_run_c1bed30/`。这仍不覆盖并发读写的全部交错或压力。

增加 fork 后 exec 的正常 Xsh 探针：父进程持有两个终端别名并设置 CLOEXEC 和
模式；子进程先验证失败 exec 后会话可用，再成功替换自身镜像；新镜像检查别名、
CLOEXEC 和共享模式，runner 比对子进程前后 PID，父进程再核对自身会话和描述符。
提交 `42bb4db8328dbec3d5bb73a861614416879a6c03` 后重建并在正常 Xsh 客体执行，
该子集通过，子进程 PID 替换前后相同，父子描述符和模式检查通过。build ID
`13cc473adb4d7bea`，系统 manifest SHA-256
`66046965490a74e5d0b5454a753fa5a7c5eefdf00f44ff40d91e4a5e4d560186`，镜像 SHA-256
`a521f7b054c8526f6c8ddde26f6a02e356021c4232b313cf92554193f2b9d8f5`，SDK 树 SHA-256
`9a01f3b3b664134e8dd43fd84035ef42924480bc41d8ead945d027cbc45f741d`，串口 SHA-256
`4fcb0be854b17d2d44e088b82413143ea0b7bac280e12378d3a6cc96995071b6`；报告位于
`build/w1_fork_exec_run_42bb4db/`。不推断在途请求竞争或多线程 fork。
