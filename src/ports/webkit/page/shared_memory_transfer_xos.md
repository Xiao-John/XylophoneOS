# ClarkE 的 WebCore 跨进程位图借用

在软件 WebCore 配置中，依次应用 `software_context.patch`、`software_buffers.patch`、
`software_graph.patch`、`shared_memory_xos.patch`、`shared_memory_transfer_xos.patch`。
补丁采用现有的 XOS sys84 端点和 sys88 grant 权限，并以单调时钟限制接收等待。客体夹具通过
sys86 服务名建立端点。编译使用同一 WebCore 生成图和 XOS glibc C/C++ SDK，交叉头沿用
[本地共享页](shared_memory_xos.md)的布置。原生 SDK syscall 实现须参与链接。

## 建立借用

受信启动器必须先确定稳定的生产者和持有者身份。双方各持同一专用通道的发送端与接收端，
并从启动上下文取得对端 PID 与本次交换号。常规 `SharedMemory::allocate` 只提供本地
映射。调用 `allocate_for_xos_transfer` 并创建 WebCore 保护类型的句柄后，生产者可通过
`xos_memory_offer::send` 发布一次借用。持有者调用 `xos_memory_loan::receive`，
由原生 `SharedMemory::map` 建立视图，并用同一块内存创建软件 `ShareableBitmap`。
只有读和按选择的写权限会传给持有者。委派及管理权保留在生产者进程。

收发前分别向内核核对两个端点的对端 PID。线上的 32 字节记录携带交换号、grant 编号、
显式长度和授权类型。真实映射由当前进程的内核句柄表检查。已有 ABI 分别完成端点查询
和 grant 委派，信任边界包括由启动器选定、在交接期间维持身份的对端进程，以及通道中
有序、串行的一次交换。消息正文只能选择当前进程获授的 grant。通用 WebKit2 IPC 编解码
以及把来自不同授权上下文的匿名引用混入同一通道，仍需单独定义并验收。

## 正常释放与退出

- 持有者清理位图、映射和句柄后调用 `release`。如果同一进程的 WebCore 引用仍活跃，
  返回 `local_views_active`。解除这些引用后可以重试。
- 生产者经 `confirm_map` 确认持有方曾成功映射。收到 `release` 回执，且本地引用
  清理完毕后，`close_after_release` 执行内核管理关闭。持有者用 `confirm_close`
  核实关闭回执。闭环之前生产者保持自己的管理句柄。
- 持有者先退出时，内核回收该进程的映射、句柄与端点。生产者确认退出并清理本地视图后，
  调用 `revoke` 关闭剩余的 grant。
- 生产者先退出时，内核回收生产者的映射和句柄。持有者原有映射与页在该持有者退出前
  继续有效。初始 ABI 将持有者的独立句柄回收交给进程退出。现场需由监督者处理失联的
  持有者，`release` 会返回 `exchange_unconfirmed`。
- 委派成功而发布未确认时，`send` 保留 `published() == false` 的管理票据，供生产者
  在确认安全的时点关闭。协议中途失联且持有者可能仍在使用视图时，生产者要等待受监督
  进程退出，再调用 `revoke`。管理关闭会撤销双方所有映射，调用者负责关闭顺序。

该范围只覆盖单 grant 的 CPU 位图。原生 64 页上限与软件像素布局保持一致。大视口和
通用长期借用的传输策略仍待独立验收。

`tests/fixtures/webkit/shared_memory_transfer.cpp` 使用两个真实客体进程，对 16×8
软件位图验证两条完成路径以及双向退出顺序。目标回执须记录 SDK、补丁、夹具与 ELF。
以普通系统镜像和上述构建结果运行客体验收：

```sh
python3 tests/webkit_shared_memory_transfer_guest.py --target "$TRANSFER_OUT" \
  --system "$SYSTEM_OUT" --output "$GUEST_OUT"
```
