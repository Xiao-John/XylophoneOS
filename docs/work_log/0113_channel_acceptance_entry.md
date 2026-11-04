# 0113 — 通道定向验收入口

2026-10-30。用户授权自选任务，选择 W1 通用通道的可执行验收准备。
独立分支 codex/channel_acceptance，基于 W1 87d2179；未合并远端 main，
不修改内核、ABI、其他用户态移植或 localpilot。文件由主 agent 独占。

## 已完成

tests/w1_wait_smoke.py 新增 --probe channel，默认 wait 保留原流程。
复用提交状态守卫、源码/镜像/SDK完整性校验、交叉构建、私有 FAT 测试盘、
串口和失败回执。channel 使用 exec-driver 显式授予父进程 spawn 权利，
子程序仍通过自身身份枚举和收发；不因探针名称在内核授予权限。

channel_probe.cpp 在原双向通信/枚举身份/退出失效基础上加入每控制者4通道
配额、关闭额外通道及旧句柄拒绝、短接收缓冲失败后消息仍可读取。
这些是新增断言，不是已取得的运行资格。

## 验证及边界

--help 与 Python AST 检查通过。使用现有隔离 SDK
build/w1_generic_channel_20261029/sdk 交叉编译并静态链接成功；实际命令在
build/channel_acceptance_20261030/receipt.json。ELF SHA256：
fac0e94116c13e70ae84a2676f00a0bb2642d4664b71fcb28d480edab558d128。
旧 SDK 的这次使用仅证明探针可链接，不授予新组合 SDK/系统资格。

客体 NOT_RUN：遵守全部相关修改提交后才验收的约定；新探针/runner 改变
系统源码 manifest 输入，需要新构建，不能拿旧镜像通过入口守卫。
fork/exec、故障、阻塞等待者被关闭、并发发送及压力仍未覆盖。

下一步：在相关 W1 修改已提交并完成当前宪法/ABI整合后，用私有目录构建，执行：

```sh
python3 tests/w1_wait_smoke.py --probe channel --system build/NEW_SYSTEM --output build/NEW_CHANNEL_RUN
```

不将本组称为通道客体验收、生产 Broker、终端服务或 W1 完成。
