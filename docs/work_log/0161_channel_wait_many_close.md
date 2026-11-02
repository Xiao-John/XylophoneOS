# 多通道等待中的对端关闭探针

终端服务未来要动态管理多个应用端点，必须在端点关闭时从等待集合中安全撤除。
在既有 sys81 探针上增加两个真实进程间的受控顺序：父进程等待两个空接收端点，
子进程先确认握手，再延时并关闭其中一个端点。父进程要求阻塞等待因关闭返回 0，
随后重查返回 denied；另一端点仍可显式关闭。该测试验证这一特定关闭路径，不证明
并发发送、故障清理、多会话仲裁或完整 W1。

提交 `eb68f26e8ff85ffc2419d28bff8073b2ec0befcc` 后重建并运行客体探针，结果
`passed_subset`，包括阻塞时对端关闭及失效重查。build ID `8fdde83bebceda1e`；
系统 manifest SHA-256 `61ea268cfad3dcb0ac5b064f97b87055afabf99abc4ae7355aabbfc2b87e0c5f`，
镜像 SHA-256 `8ef176afcef2c99a736b94f202051fec0b7737c7e41f8c91697c0574fd7a91d6`，
SDK 树 SHA-256 `4f7a70c97ceb32c2598888a764206f440f8b689490bb8bcf45b05ec7cdf529ce`，
探针源码 SHA-256 `530ba07098bf53b1200015406a223cbf394900412734da098b1228e2f2cc73ce`，
串口 SHA-256 `89b6fa7fdd184489969948bf75f42e6d1eec4b2beb4a10d700a31a76d9a671ac`。
报告与串口位于 `build/w1_channel_close_run_eb68f26/`。单通道阻塞关闭、fork、
故障清理、并发发送、资源压力和完整终端仍未由此覆盖。
