# 32dbebc0 · Pumpkin broker deadline separation

2026-11-26。以 [#255](https://github.com/Xiao-John/XylophoneOS/pull/255) 已发布
的 `da01e594` 为基线。受测修复与公开提交 `598502741b8295fd2e73918d7c7575a70d7b01b8`
的 Git 树 `f3658f1478f20ee66fa5e80ce04c100337efe9d7` 一致。保护独立 broker 的共享服务间通道，
并用实际接收时钟判断单条普通连接是否到期。

客户端授权期限仍在私用服务请求中传给 daemon，取原请求和本地连接的较早值。
broker 另从发出请求时计算有界的服务间接收期限。在服务期限内收到正确回复时核验
并消费它。如果客户端已到期，丢弃该次结果，下一次授权继续使用原通道和递增序号。
服务回复未能确认才撤销共享通道。broker 在读取客户端消息后重新采样时钟，连接
到期时直接结束该连接，避免继续授权或读取。 [资源服务契约](../contracts/pumpkin_resource_service.md)

## 执行检查

```sh
python3 -B tests/pumpkin_daemon_loop_host.py --sanitize
python3 -B tests/pumpkin_host.py --sanitize --target-cxx x86_64-elf-g++ --output build/deadline-core
python3 -B scripts/build.py --output-dir build/deadline-system
python3 -B scripts/build_pumpkin_daemon.py --bridge-probe --sdk build/deadline-system/sdk \
  --output build/deadline-fixture
python3 -B scripts/build_dash.py --sdk build/deadline-system/sdk --receipt build/deadline-dash.json
python3 -B tests/pumpkin_daemon_guest.py --bridge-probe --system build/deadline-system \
  --fixture build/deadline-fixture --dash-receipt build/deadline-dash.json --output build/deadline-guest
```

受控时钟下运行实际 broker 路径。过了客户端时限、在服务时限内送达的回复被正常消费，
文件没有读取也没有客户端结果，紧随其后的正常请求继续在同一服务通道上读取。模拟
正常连接在接收时到期，该次不发出授权请求。模拟服务无回复，直到独立接收期限才关闭
服务通道。原 daemon 回复队列检查、ASan/UBSan 及独立目标对象编译通过。

QEMU 11.1.2 在普通镜像中执行原跨服务回归。xsh 和同 SDK 构建的 dash 分别通过
13 项关联及退出检查，每轮恢复 `[129711, 3, 1]`。材料审计通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `a85cd219df9c1e5f` 清单 | `9ec2cd88e32159d5aab78b7a53b4c7fa7cd004238813522fe71f26c47718ca7e` |
| 系统 ISO | `68aca3b42c653bed332ea609a0eaaa949cbffeff150424082cd7fd7a8718b297` |
| `build/deadline-fixture/receipt.json` | `3699a3073abdc3350a2466e391058bf408c47045ff32bc8e07eebe6899421c4d` |
| `build/deadline-guest/report.json` | `817c6b8648370746797cd18e5d4ac9c52779542b005589e4a853b9c944cc6319` |
| `build/deadline-guest/guest_serial.log` | `7b537c32cf8077545fc45ce8218c6558e929691c3d5fae45725a13f5eac40cf0` |
