# 受批准动态 closure 与易失激活控制器

`xos/dynamic_launch.hpp` 是 P0 公共动态加载器的闭包获取层。它使用
`dynamic.hpp` 的身份与 generation 校验、同一 readonly file pin、完整 ELF
预检器和启动控制器的 admission callback。仅凭相邻 manifest 或 ELF note
不能调用它获得新的批准。

## 批准与选择

`configure(policy, absolute_deadline)` 接收由受信原生启动者明确提供的最多四个
generation 根、各根 manifest 的规范绝对路径、SDK 摘要、当前索引、sequence
和撤销位图。根 ID、摘要及路径互不重复；未知保留位和未使用槽非零均拒绝。
政策只能成功安装一次，之后不允许用重新 configure 清空撤销记录。

安装前打开、完整验证当前 generation 的所有对象、依赖和版本，再确认所有
临时 pin 已关闭，才发布当前政策。`activation_catalog::restore` 支持只读
启动 capsule 携带的既有 sequence/revoked 状态；它验证该状态且不能覆盖
已初始化 catalog。此复制不是与父控制器之间的实时同步协议。

`acquire(path, deadline, closure)` 只选择当前已批准、未撤销根。manifest 在
同一个 pin 上读成私有快照并验证完整摘要；精确 main 路径不同才返回独立的
`error::not_selected`，供公共入口继续旧静态路径。畸形路径、manifest/ELF
错误、摘要不符和撤销均不能冒充该回退信号。`acquire_index` 用于预检某个
明确已批准索引，不隐式切换 active。

## 同一 OFD、预算与期限

每个对象以 `read_only | open_pin` 打开；随后 fstat、完整 SHA-256、note、ELF
几何、动态表、依赖与版本检查，都从该句柄读取。成功时 caller 保留这些 pin
用于最终映射或显式转移给 child，绝不按路径重新打开已验证对象。

4 KiB 缓存只缓存该不可变 pin 的字节。fill 使用有界 read_at，并且每次缓存
读取也复核绝对单调期限。全部 Files 操作使用同一个截止时间，manifest 的
startup_budget_ns 只可从 acquisition 起点缩短它；不会为每个对象重置预算。
对象仍受 generation 的数量/总字节/映射预算约束。动态映射上界保留末端
4 GiB 区域，不能与公共启动代码的固定早期 heap 碰撞。原生 C++ 所需的 `+`
允许出现在规范路径分量和 SONAME 中。

`release` 只有收到成功 close 答复才清掉对应 token。正常成功可重复调用；
它保留 generation、ticket 和 pin 元数据供提交失败清理。manifest pin 也
保留在 closure 中，不能因关闭结果不明而落在栈上丢失。发生未知 I/O/超时
结果或 close 失败时，closure 保留未确认 token 并进入 quarantine；不得复用
存储或自动重放副作用。未知传输结果也阻止该进程继续发起新的获取/激活。
进程结束时由现有 Files 生命周期回收，不能把 init 当成恢复会话的手段。

## 激活、回滚、撤销

`activate(index, expected_sequence, deadline)` 对候选重新执行完整闭包预检，
完成所有临时 pin 清理并复核总期限后，才原子更新 active/sequence。任何失败
保留原 active 和 sequence。显式选择先前批准且未撤销的根就是回滚。路径
内容在预检后仍可能被替换，下一次启动会重新 pin 并检查根摘要；预检不代替
实际启动自己的 pin。

`revoke` 使用相同的 expected_sequence 防止丢更新。撤销 active 后不再产生
新的 capture；选取另一个未撤销批准根才能继续。启动控制器的 admission
callback 在 PREPARE/READY 检查请求根的当前本地撤销状态；运行中的旧根可以
迁移到另一个批准根，清理消息仍遵循启动控制器的独立规则。

政策/文件客户端由 PID try-lock 串行化，同 PID 竞争返回状态错误或 busy。
fork 可以接管不同 PID 的私有复制锁，但保留的政策只是 fork 时快照。该层
没有持久防回滚、分发签名、跨后代撤销广播、进程树配额或在线更新守护进程；
这些仍属于 P1。公共 GNU runtime 的组合资格另行记录。
