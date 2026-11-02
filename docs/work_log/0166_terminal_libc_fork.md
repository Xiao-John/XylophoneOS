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
`build/w1_fork_cap_run_179c668/`。此结果未区分哪个资源先耗尽；后续增加先单独 prepare、
核对通道对派生明确返回资源不足并 abort 的断言，提交后须重新执行客体。
