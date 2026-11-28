# glibc Net2 有截止的就绪等待与写半关闭

基线 `a2a33b8`（原生 readiness/SHUT_WR）。本模块不修改共享 `docs/state.md`。
有截止等待依赖通用 IPC absolute-deadline 模块（PR #403；本地验证来源
`96d75c9`、`545a5cf`）。该依赖在独立组合树验证，没有混入本模块的产品 diff。

## 行为

静态 glibc 将 `poll` 和 `shutdown(SHUT_WR)` 接到真实 Net2 扩展。一次正超时
只建立一个调用者绝对期限，涵盖 FD 锁准入、网络会话锁、capability/readiness
IPC 及等待。sys85 的 receive_until/send_until 允许服务进程仍活着但不回复时
按调用者期限退出。旧内核拒绝新模式时，在发送新服务扩展请求之前返回
EOPNOTSUPP；原阻塞 TCP 子集保持可用。

到期时只保留已发送的只读查询及其原 sequence、会话代际、handle 和独立
transport 期限。下次调用精确消费迟到结果，再推进序号；不会因 poll 超时
重放查询、销毁连接或重放 send/shutdown。副作用请求交付后丢失结果继续采用
原会话失败语义。损坏响应、对端失效和 transport 到期均有明确失败路径。

poll 清理通过非阻塞引用队列退出，不执行远端最后一次 close。保留的引用
防止并发 close/reuse 把在途操作改指向另一对象，后续正常运行库调用负责回收。
SHUT_WR 在 dup 别名间共享；之后 send/write 返回 EPIPE，读侧继续接收数据与 EOF。

## 验证

使用已核验的 `xos-sdk-preview-2-linux-x86_64` pre-release 常规 launcher；没有
声称 `--offline` 命名空间隔离通过。两份 SDK 均从签名核验的 glibc 2.44 重新
构建，产物、源码、系统镜像和测试 ELF 的完整收据分别绑定。lwIP 使用仓库锁定
2.2.1 archive 与补丁。

- 实际 libc C 桥的注入边界测试通过 ASan/UBSan：单一绝对期限、迟到 capability/
  readiness 仅消费一次、无超时隐式 close、FD lease/reuse、重复半关闭、旧内核、
  旧服务、损坏响应和混合非法 FD。LeakSanitizer 未运行。
- 实际 FD/session 59 组和真实 Files/FatFs 15 组通过 ASan/UBSan。新增的延迟
  引用回收用例验证 poll 收尾不执行远端 close，96 次 socket 回收不耗尽路由槽。
- **旧内核**镜像 `a1822e5aa44d66c8`：9 个真实 guest 用例；4 轮新API明确拒绝后，
  原 TCP 仍完成随机 challenge、1537 字节短写尾部、EOF、别名与 FD 复用。
- **新 deadline 组合内核**镜像 `b57a29f32c000699`：12 个真实 guest 用例。测试
  peer 保持认证 IPC 和进程存活，故意等待 1 秒才回复；40 ms poll 实际耗时
  **40,000,000 ns**，下一次 poll 正确消费迟到回复。服务观测 capability 和
  readiness 各恰好 1 个请求，证明未重放。这一 fixture 仅证明 IPC 时限。
- 同一组合镜像另外启动真实 lwIP/NIC 服务两轮：4 轮双向 TCP 随机 challenge，
  2 轮对端收到客户端 FIN 后才发送随机响应的半关闭挑战；就绪、30 ms 空等、
  EOF、错误 PID、拒绝地址、关闭端口、服务重启及逐用例资源基线均通过。

证据：[摘要](../reports/glibc_net2_wait_20261127/summary.json)、
[新内核 guest](../reports/glibc_net2_wait_20261127/deadline_guest.json)、
[旧内核 guest](../reports/glibc_net2_wait_20261127/legacy_guest.json)、
[校验表](../reports/glibc_net2_wait_20261127/manifest.json)。公开导出使用路径占位；
原收据字节哈希和导出后哈希分开保留。

开发中保留了两个失败收据：未初始化 FD 表前检查越界 fd 的顺序错误，以及
测试 peer 在 close 回复后把客户端正常退出竞争误判为失败。前者已修正生产
准入顺序；后者仅调整 fixture 收尾，仍独立要求客户端 close 和进程成功退出。
两份最终系统均从修正后的源码重新构建并重新跑完整用例。

## 明确剩余边界

这是有限 profile，不是完整 POSIX poll 资格。最多 32 项，仅 TCP 与普通文件；
connected TCP 的 `poll(..., 0)`、pipe/terminal 和未列出的事件返回 EOPNOTSUPP。
没有伪造零等待快照，也没有将服务健康时的及时响应冒充超时保证。负超时仍受
既有 transport 生存上限约束。

事件订阅/通知缓存、零等待 TCP poll、非阻塞 connect、完整混合 FD 等待、
SHUT_RD/SHUT_RDWR、SIGPIPE 和更广同进程并发验收进入下一轮。此批 guest
使用 xsh；Dash 和后续 quota 总组合尚未在这些镜像重跑。DHCP、公共 CA、公共
互联网兼容性没有由本模块获得新增资格。

## PR 公开附件调整

自动审批审查拒绝公开大型压缩 SDK/系统构建清单。公开版本省略这四件载荷，
保留原件 SHA-256 和必要的源码、工具、镜像与程序绑定摘要；完整原件保留在
独立开发树用于核对，没有通过其他渠道公开被拒载荷。两份串口日志改成完整
可读明文，仅规范化行尾/终端尾部空白。生产代码、测试代码和所有实际结果
均与 `95a2b54` 相同。公开附件选择变化由 export.json 和 build_binding_summary.json
记录；平铺 manifest 重新绑定实际公开文件。
