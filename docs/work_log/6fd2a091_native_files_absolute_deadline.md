# 6fd2a091 · Native Files 绝对期限与同会话失败锁存

公开动态 loader 的总启动期限不能依赖原生 file client 的 8192 次 yield。
本模块补上有限绝对期限入口，并保持 libc/native loader 使用同一个 Files
会话。API、兼容边界和错误语义见
[Files deadline 契约](../contracts/file_transport_deadline.md)。

`file::client::set_deadline` 使传输在发送前、接收后和 blocked wait 中检查
同一绝对时间。原生 fallback 使用既有认证 Files reply wait；旧内核回退
使用真实单调时钟/sleep。发出请求后失败会锁存到进程共享状态，不能用另一
client 或 `init` 清掉。发送前过期仍可恢复。

glibc 新 hidden exchange hook 把期限传到 cwd/session 锁、初始化及既有 G3
请求实现，不复制 session owner 或 sequence。新 SDK 本地错误 `-1001`
与 Files 既有 `-13`（名称过长）分离。只有带匹配 finite-lock hook 的旧
newlib 会话锁才能采用此入口；当前缺失时明确拒绝，不把无限等待藏在期限内。

## 实际验证

开发与验证命令在 SHA-256 已核验的 SDK Preview 2 中运行，归档摘要为
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。

```sh
xos-sdk --workdir "$SOURCE" python3 tests/native_file_deadline_host.py \
  --output build/NEW_NATIVE_DEADLINE
xos-sdk --workdir "$SOURCE" python3 tests/glibc_g3_files_host.py \
  --output build/NEW_G3_DEADLINE
```

| 验收 | 结果 |
|---|---|
| 原生真实 client、仅替换内核 trap | 13/13 通过：正常/发送前过期/就绪/期限/旧内核 sleep/期限处回复/发送失败/端点关闭/错误 magic/sequence/长度/状态/短报文；超时后跨 client 与 init 拒绝复活 |
| G3 生产 FD/session、注入内核/服务 | 62/62 通过，新增发送前恢复、cwd 锁期限、同会话正常回复、超时使 native 与 libc 同时失败 |
| G3 + 真实 Files/FatFs 实现 | 15/15 组通过，覆盖原有匿名文件、seal、块请求、共享游标、unlink 后引用、追加、目录、额度及全回收 |
| 编译 | 宿主严格 `-Wall -Wextra -Werror -Wconversion -Wshadow` |
| 本模块独立 QEMU | 未运行；后续公开 loader 组合客体必须使用本入口，不能把本次 host 结果写成端到端完成 |

[平铺证据索引](../reports/native_files_deadline_20261127/manifest.json)绑定命令、
输入 SHA、实际结果及导出前原始摘要；完整日志保留在 build 目录。
本次没有更改 kernel/File service ABI、公开 spawn/exec 的动态接受政策或
glibc 默认发行资格。真实 ELF、capsule、ready/ACK、exec 和 SDK 资格仍为 P0。
