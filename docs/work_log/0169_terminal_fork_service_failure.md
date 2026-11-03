# 父子终端会话中的服务故障探针

已有服务故障探针只覆盖一个应用进程。现扩展专用 supervisor 的受控场景：有限授权
的应用 fork 子进程，父进程输出就绪标记后通过管道允许子进程读取终端，父进程等待
子进程；supervisor 延时杀死终端服务。探针要求子进程读取报错并退出，父进程随后
对自身终端的读取也报错，supervisor 回收并重新授权服务。不能将固定延时解释为证明
子进程一定已进入内核阻塞，也不推断所有故障顺序或消息是否执行。

提交 `3ec5a6ebcab484c9154d00d20a0dbe6257395246` 后重建专用 supervisor 系统、
使用核对源码输入与回执的 UTF-8/ncursesw 组合 SDK 重新链接消费者，并以独立测试盘
在客体运行。结果 `passed_probe`：父子终端请求均报告故障，服务回收重授权成功；
同组宽字符、locale、重入和服务重启探针也通过。build ID `a625cd7de1396176`，
系统 manifest SHA-256 `9da68dcb41ee8aea1ff2db2635440d1bac11dba9f0e5d41efa32f651ea1fd37b`，
镜像 SHA-256 `a18dfc1010c159d34d13738b0de15cecc6ab8b51a75e1e39f8784fabe1a1ab62`，
组合 SDK 树 SHA-256 `038491cd8cefcc77551b681b3954e20983d979f7d1d32a4df7bf982bf0fd27d0`，
串口 SHA-256 `51c9bb80fcdb24b9e8e07646ed52fc16bc56d749fa46b362553e2702477ec540`；
报告位于 `build/w1_fork_fault_3ec5a6e/`。这是专用 supervisor 的受控子集，不是正常
Xsh 故障时序或完整 W1/W2 资格。
