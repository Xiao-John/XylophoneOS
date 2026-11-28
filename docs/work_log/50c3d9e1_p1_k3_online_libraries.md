# P1-K3：显式 online GNU 库的实现与目标资格

## 交付结果

独立 online profile 已完成实际目标验收。默认 fixed-startup profile 仍明确
拒绝运行期 dlfcn 调用；online 路径只消费启动前已经验证并保留的不可变
Files pins，不从路径搜索、环境变量或相邻 manifest 取得新执行 authority。

实现和格式边界见 [online 契约](../contracts/online_libraries_v1.md) 与
[ABI 分配](../contracts/abi_registry.md)。完整结果、原始身份、失败历史与
逐叶哈希见 [资格报告](../reports/p1_k3_online_libraries_20261128/README.md)、
[qualification.json](../reports/p1_k3_online_libraries_20261128/qualification.json)
和 [manifest.json](../reports/p1_k3_online_libraries_20261128/manifest.json)。

## 实现决策

GNU loader 继续负责依赖、版本、引用计数、构造/析构和 TLS unload interlock。
native 层提供有界映射及原 Files 会话桥接；同线程递归和 Files I/O 使用一个
五秒绝对期限，不能逐次续期。该期限不强制中断应用构造/析构函数。
base 之外同时只有一个受限、无 TLS 的 private namespace。批准 pin 保留到
进程退出，dlclose 不承诺立刻返还 pin credit 或解除仍被 TLS 析构保留的映射。

新的 entry handoff 完整复制四个 online 字段。真实 native worker 的动态 DTV
在 TLS 析构之后退休，由仍活着的 libc 线程清理，避免在 TCB 已回收后继续
访问它；最后 worker 的当前 TLS/DTV 保留到 GNU 进程退出回调结束。
在线对象拒绝 static TLS、TPOFF64 和 TLSDESC；实际 GNU 的 TLSDESC 可能走
静态 TLS 分配，现有 native worker 注册边界不支持这种在线扩展。

## 实际验证

冻结生产源码为 `86d39b31ade96ba7a609b9321e30ee63c0632441`。公共
[源码锚](https://github.com/Xiao-John/XylophoneOS/commit/0031e986cc79f0bb1d1f61a626def6a65d9dfb68)
具有完全相同的 Git tree `94b1936c987f9b8662ef26e8b8f49bca38b1cb7a`；
原始构建/运行收据中的本地 commit 没有改写。

Native system `94674a7e28151485`、新编译的 GNU runtime v2 和独立重编的
匹配 unwinder 通过七次冷启动、16 项实际用例。所有用例都精确恢复
129790 free pages / 2 tasks / 0 completions。测试涵盖依赖/namespace、并发、
已运行 worker 的动态 TLS、lazy TLS、pthread_exit、最后 worker 的 on_exit、
路径替换后的原 pin、拒绝策略、循环卸载、默认 fixed 拒绝、缺失/替换对象、
正确成形但 provider 不满足的版本，以及真实 ELF 上两种不允许的 TLS relocation。

6 组 mapping/worker host 运行和 60 项生产 closure/verifier 检查也通过，
包含普通模式与 ASan/UBSan。LeakSanitizer 未运行。完整 source、两套 SDK、
运行时/展开器、五个 controller、两个 program stage 和最终 guest 输入均
在导出前再次核验。构建收据仍为 built-not-run，目标运行结论保存在独立报告。

## 保留的失败与修正

最初的 FAT32 大小不被现有夹具支持，随后一次实际启动暴露了 entry handoff
漏复制 online 字段。这两次原始报告均保留为 failed。一次程序构建使用了
当前组合不可用的 atexit 夹具，改为实际 GNU on_exit 后重新构建。
后续诊断执行通过前面的 13 项检查，却因版本变异夹具只更新了共享名字的
一个 Vernaux hash 而整体失败；修正会更新全部共享引用，生产预检和最终
guest 才得到预期的 provider-version 拒绝。该诊断仍为 failed。

最终所有产物、源快照和日志保持其原始字节。公开 JSON 只把明确的环境根
替换为重播模板，串口日志采用无损 gzip；转换记录保留原始报告与串口身份。

## 与主线集成的边界

本次执行采用冻结 v2 capsule runtime，不能重新标记为默认主线 v3 的组合
资格。单独集成到主线时保留 catalog authority、三身份实时准入、K1 sleep
导出、19 个 native runtime 输入及 v3 ABI domain；这些源码/host 复核不
替代新组合的实际运行。C++ online DSO、SMP、物理硬件和其他 P1 profile
组合保持未验收状态。
