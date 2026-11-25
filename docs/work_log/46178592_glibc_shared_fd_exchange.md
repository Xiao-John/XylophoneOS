# glibc G3 shared FD leases and authenticated files exchange

2026-11-25 · 基线 `5984573`（G3 files + source authentication）。本独立
checkpoint 提供进程启动、目录流和定位读写共同需要的内部生命周期接口。

## 实现

- `__xos_file_lease_acquire/release` 保留具体 open-description 的引用。
  调用者关闭或重用 FD 号码时，已有 lease 仍指向原对象；最后引用负责关闭
  远端 handle 或内核 route。访问模式在获取时检查。
- `__xos_file_exchange` 复用原有 files session 的锁、单调 request ID、
  5 秒绝对截止时间和失败锁存。输出在失败时清零，已投递请求不自动重放。
- `xos_file_session_exchange` 是 freestanding native loader 的窄 C hook，
  将 libc errno 返回值转换为既有 `file::status`。native SDK 未链接此 hook
  时保留现有传输；glibc 不注册旧的 lock/request-id weak hook。
- 响应校验覆盖 transfer、cwd 字符串、定位读写形状和目录记录。目录旧格式
  保持兼容；经 files-extra 模块认领的 `list_identity` 格式同时验证真实
  inode、严格递增 cursor、记录边界、条目数和 UTF-8。畸形响应锁存会话失败。

本 checkpoint 的 lease/path/exchange 是隐藏的 libc 内部接口；其 C wire
视图继续由 host 测试与共享 C++ ABI 检查。目录、pread/pwrite 的公开实现及
files 服务新操作由独立 files-extra 模块提交。

## 实际验证

```sh
python3 tests/glibc_g3_files_host.py --output build/process_files_api_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/process_files_api_sanitize
```

两轮各通过 **33 个生产 FD/session 状态机场景和 10 组真实 files/FatFs 集成**。
新增场景验证 lease 下 FD 号码复用与独立 offset、错误输出清空、native 错误
映射、两种目录格式、坏 cursor/inode/UTF-8/count/长度的失败锁存。
ASan/UBSan 全部通过；LeakSanitizer 在当前 ptrace 环境无法运行，命令明确设置
`ASAN_OPTIONS=detect_leaks=0`，资源回收由实际 close/handle quota 断言检查。

原始报告和日志见 [glibc_file_api_20261125](../reports/glibc_file_api_20261125/manifest.json)。
宿主仅替换内核 trap/IPC 边界；本 checkpoint 尚未单独进行客体验收。后续
files-extra 和 process 模块会在来源绑定的完整 SDK/系统中验证这些接口。
