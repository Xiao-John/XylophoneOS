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
