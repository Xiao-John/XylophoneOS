# COM1 授权后的 PIO 边界探针

现有负向探针证明未授权进程不可访问 COM1，但不证明授权窗口边界。专用 supervisor
在终端服务启动前，依次为独立子进程授予 COM1：窗口内读取 LSR 和 scratch 寄存器
应成功；起始地址低于或高于窗口的字节读取，以及起点为窗口末尾、跨越窗口的
16 位读取，应触发 #GP。每个进程退出或故障后先核对隔离，再显式 recover；全部
检查结束后启动真实用户态终端，确认后续设备交接仍可进行。被拒绝的端口指令不得
实际访问设备；本探针不写硬件寄存器，也不假设其读取值。

runner 在提交后的匹配系统 SDK 中编译独立目标 ELF，记录 fixture、SDK 与 ELF 哈希，
用独立测试盘执行；不将宿主编译当作客体验收。此范围不验证 fork/exec 权限撤销、
多线程切换、IRQ 应答竞争或完整 W1，须另行覆盖。

提交 `cc4639a14dc4f3c83537c52b2c0d5fd7b30c5f98` 后重建并在专用客体执行，窗口内
读取成功，低/高越界和 16 位跨界均触发 #GP，后续终端交接与 fork 子集通过。
build ID `545f56cc8e7beec4`，系统 manifest SHA-256
`eac97182fb47db9e253aa7137a9c53f6f2ff6ef75534580e2aa2b3a4d438b793`，镜像 SHA-256
`0103a9618fb2cac8115cfc6aed27b676a8eb4d4afa1f64dcb239526ca53c3632`，SDK 树 SHA-256
`911d361a116a1bf4ea1f743cbb1d6e88d773163106dd482bf75aed0a44a73ef7`，串口 SHA-256
`5438a879f96e5b001febc2987abd48640185c70572c6462083f8dcc640499493`；报告位于
`build/w1_pio_bounds_cc4639a/`。

扩展专用探针：授权者 fork 后子进程访问 COM1 应 #GP 而父进程权限保留；失败 exec
后原权限保留，成功 exec 后原权限失效且访问应 #GP。提交
`a0600484f373269ae2824455496a3c9fdc794684` 后重建的专用客体检查通过，亦重新通过
窗口内外、跨界、后续终端交接及 fork 子集。build ID `3d971bcdae986aa0`，系统
manifest SHA-256 `c04a046baafd285423562820bc933fcd77c5b76219809c59e548018b034dd5c3`，
镜像 SHA-256 `0bd1553e929883020cb15becd7ada1c1725c7a9d2964759291cb73718c43b6e8`，
SDK 树 SHA-256 `3cb3c0e668d60b6a54149fdf0b5f9d74d8a7a5042fb29dad8998bf25c09d22d7`，
PIO ELF SHA-256 `74d01d32839463bc49d23d31bd998107344cffc47a0c05736c5265917a719afe`，
串口 SHA-256 `7d4bf4b2a3043810dfa3a0e3d6459f4f6d5ed2676ade858861682d98bfc3ea64`；
报告位于 `build/w1_pio_lifecycle_a060048/`。仍不涵盖主动撤权竞争或多线程切换，
亦不能将这组结果视为完整 W1 资格。

新增主动撤权受控时序：授权进程先读取窗口内寄存器，并经双向受控通道通知
supervisor；supervisor 撤权、确认隔离后再发送继续消息。进程恢复运行时应看到
controller 查询被拒绝且下一次 COM1 读取触发 #GP，随后 supervisor 回收并重新
授权终端。该检查验证一次明确的撤权后调度顺序，不证明所有在途 I/O 竞争或 SMP；
提交 `fd8d478d8affe1fbd33fa0b48c98085b81c97ac2` 后重建的专用客体检查通过；
build ID `3983726c8710d469`，系统 manifest SHA-256
`e4720b24dcfe6e1ebeb5470b1cadbfbbfe95b63b96b738a0dac1953e20f7db37`，镜像 SHA-256
`94a82f76cff948f6beef2756ddc699f56db1453b6aed19af5c143da1d613bb68`，SDK 树 SHA-256
`00d2eac7acaf1f718d8fb2f8acdabd09cf3de0a24faaf80d6b20b3509ed2d87e`，PIO ELF SHA-256
`303ecc85c8e295a2dfcfe2057d536906aa55f9a7d60f7a32139b7fb2241cbb33`，串口 SHA-256
`62424b20b4e3474d1d1a2bb2803713415f0e09ecef3f7a07fdc9143c0271bc0e`；报告位于
`build/w1_pio_revoke_fd8d478/`。

增加单核多线程探针：授权进程的工作线程先读 COM1 并通知主线程，主线程在一次
线程切换后也读 COM1；supervisor 撤权后，主线程唤醒原工作线程，其再次访问应
触发 #GP。探针使用无 libc 的机制线程核心，runner 从匹配源码编译并记录哈希。
该检查验证一个线程切换及撤权后的线程访问顺序，不覆盖 SMP 或全部交错。提交
`6d557320b9e7595180da81548b9afab5cc2429fa` 后重建的专用客体通过该检查及既有
PIO/fork/exec/终端交接子集；build ID `0c5789a68c601257`，系统 manifest SHA-256
`6f4f058666a848f9fc64b1edf628a5af45892e1a366cbe6ea19edc0e3f6d679e`，镜像 SHA-256
`056ef9795d6084d1fc8d21e24e000e6d6c3e823cb26391e3219a6bdf91012b5d`，SDK 树 SHA-256
`4d185c9d1c052a065476f8f940d212414b70c373f86f0fff746f45a43269f53a`，PIO ELF SHA-256
`dd4076533faae777d116d38392854e09f67b1f5b34400bf584f7b8dd5b6b0c47`，串口 SHA-256
`257859d2f5661646e4c0dc5cb5ae2179316b088465b0d17e00ef81371b734c28`；报告位于
`build/w1_pio_threads_6d55732/`。
