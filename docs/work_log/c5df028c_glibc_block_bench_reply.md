# glibc shared files exchange: block benchmark reply validation

2026-11-25 · PR #157 review `4694316804`，基线 `cb42fe6`。

`file::client::block_bench` 和生产 files 服务已约定：op17 成功回复没有
payload，`value` 等于请求的 `length`，合法请求为 1 至 8 MiB。公共
glibc exchange 的默认成功形状要求 `value=0`，因此合法回复会触发
`EIO` 并锁存会话失败。新增回归先在旧实现复现 `block_valid` 失败，
随后补齐 op17 的精确形状检查。共享 ABI、服务和 native SDK 语义保持原样。

## 实际验证

```sh
python3 tests/glibc_g3_files_host.py --output build/api_block_host_final
python3 tests/glibc_g3_files_host.py --sanitize --output build/api_block_sanitized_final
```

GCC 14.2.0；普通构建和 ASan/UBSan 各 **41 个状态机场景、12 组实际
files/FatFs 集成 PASS**。新场景包括精确返回值、8 MiB 上限、非空 payload、
错误完成字节数、零长度和越界请求伪造成功的拒绝。协议错误清零调用者输出，
后续请求保持失败且不再发送；合法调用后普通 open/write/close 成功。

真实服务集成运行实际 `files.cpp` 的 op17 分支，通过专用私有内存磁盘读取
513、4097、8 MiB，并核对每次有界块读取的次数；无效长度返回 `EINVAL` 后
同一会话继续完成已有文件语义与全部资源回收检查。测试未替换生产协议处理。

完整源码散列、旧实现失败、普通和 sanitizer 日志保存在
[block_bench 证据](../reports/glibc_file_api_block_bench_20261125/manifest.json)。
先前冻结报告保持原样。本次仍为宿主 IPC/内核边界替身；客体验收由后续组合
SDK 完成。LeakSanitizer 在当前 ptrace 环境不可运行，ASan/UBSan 已实际运行。

下一步将本提交同步到 process 和 terminal 依赖分支，再各自重建 SDK，避免
把旧 SDK 与新 validator 混合归为同一资格。
