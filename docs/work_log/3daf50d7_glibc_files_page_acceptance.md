# glibc files directory page boundary acceptance

2026-11-25 · 在 `61c24b5` 的独立 worktree 验证公共 FD/RPC 接口的最终修正。
原始 [8474d27 证据](../reports/glibc_file_api_20261125/manifest.json) 保持原样。

files-extra 服务实现审阅确认：目录请求 `length=0` 使用默认 64 条上限；
空响应若同时返回非零 continuation cursor 是协议错误。runtime 按这两条
语义校验，并在协议错误后锁存当前会话失败。

新增 `directory_default_limit` 和 `directory_empty_progress` 两项生产
runtime 场景；前者返回两项有效 identity 记录，后者验证错误输出清零及
后续请求不会再次发送。

```sh
python3 tests/glibc_g3_files_host.py --output build/api_pages_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/api_pages_sanitize
```

普通构建与 ASan/UBSan 各 **35 个状态机场景 + 10 组真实 files/FatFs 集成
PASS**。新证据及完整源码散列位于
[glibc_file_api_pages_20261125](../reports/glibc_file_api_pages_20261125/manifest.json)。
报告仍使用宿主 trap 替身；客体由后续 files-extra/process 模块独立完成。
LeakSanitizer 因当前 ptrace 环境限制关闭，实际 handle/close 配额断言通过。

## native SDK 共享传输与合法短读修正

接入实际 `src/user/sdk/file_client.cpp` 后进一步核对旧 op5：客户端可请求
3800 字节，服务按响应负载上限短读 3798。公共 validator 原先误将请求
也限为 3798，会把合法短读锁存成协议错误。现保持 response <= 3798 且
response <= request；新 op30 按其独立契约仍限制请求 <= 3798。

native `client::call` 的 weak exchange hook 已接入同一 libc session。
新增场景使用**实际 native client**（同时链接生产 FD runtime）：先通过
libc 写入非同内容 3800 字节，再经 native client 读取 3798 字节，最后经
libc 读取余下两字节，检查数据、共享 offset、单一递增 request ID 和回收。
若 native client 绕过共享 hook，真实 mock request ID 检查会失败。

```sh
python3 tests/glibc_g3_files_host.py --output build/api_read_native_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/api_read_native_sanitize
```

两轮各 **36 个状态机场景 + 10 组真实 files/FatFs 集成 PASS**，证据见
[glibc_file_api_native_read_20261125](../reports/glibc_file_api_native_read_20261125/manifest.json)。
本次输入散列包括实际 native client 和全部共享/用户态 SDK 头文件；前两轮
冻结报告保持原样。验收范围仍为宿主 IPC 边界替身，客体移交后续组合模块。
