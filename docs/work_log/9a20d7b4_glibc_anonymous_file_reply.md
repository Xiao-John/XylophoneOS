# glibc 共享文件会话：匿名创建回复校验

2026-11-25。跟进 PR157 同一评审线程的匿名文件问题（追加评论 4694426577）。
基于本地 `36d5b03`，对应远端 `6538fbc7c91d7bc337754093c596c60d3894439e`。

`file::client::anonymous()` 使用操作 21，files 服务返回新句柄、inode、零长度和
空普通文件元数据。共享 glibc 校验过去只对操作 4 接受这种回复，因而将合法
匿名创建判为 EIO 并锁存整个会话。新增真实调用反例在旧源码上触发断言失败；
编译前输入摘要及失败日志均已保存。

修复允许操作 21 的句柄与身份字段，同时要求空 payload、非零有效 inode、
flags=0、size=0。其它操作仍使用各自回复形状校验。畸形匿名回复会清零输出、
锁存错误并停止后续发送；合法匿名操作之后继续正常文件操作。

## 实际验证

- 47/47 生产 FD/session 状态机宿主场景通过；同组 ASan/UBSan 通过。
- 14/14 真实 files/FatFs 集成组通过；同组 ASan/UBSan 通过。
- 匿名用例覆盖公开 native client 创建、写入、seek/read/close，零句柄、零 inode、
  目录标志、非空初始大小及额外 payload 的拒绝与会话故障闭环。
- 真实服务执行匿名创建、IO、seal、写入拒绝、close，并填满 16 个服务槽、验证
  第 17 个请求失败、全部关闭后继续普通文件操作；结束检查全部描述符回收。
- runner 在编译前冻结 55 个源码/头文件输入，最终输出 `passed` 前重新比较。
  两次正式运行输入均保持不变。LeakSanitizer 未运行。

```sh
python3 tests/glibc_g3_files_host.py --output build/file_api_anonymous_final
python3 tests/glibc_g3_files_host.py --output build/file_api_anonymous_sanitized --sanitize
python3 scripts/verify_evidence_index.py docs/reports/glibc_anonymous_reply_20261125/manifest.json
```

输出目录须使用新路径。核内 trap/session transport 由宿主 fixture 代替，files
服务和 FatFs 执行真实实现。本增量没有重新运行系统客体；修复已送入独立 G3
组合 SDK，客体组合结果由该模块绑定其最终系统与 SDK。这里的 seal 后写入按
现有 native 文件契约返回 invalid，测试没有改动该服务语义。

公开证据：[manifest](../reports/glibc_anonymous_reply_20261125/manifest.json)。
`before.json` 保留旧代码失败；`derivation.json` 记录原件摘要及路径替换规则。
