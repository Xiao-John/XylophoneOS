# c6198fee · Pumpkin identity core

2026-11-26 · 基线 `9f7a9a0f`。Pumpkin P0 在 `src/user/pumpkin/` 实现身份库、
随机凭据认证、会话生命周期与所有者策略交集。用受信适配器注入存储、熵、连接及单调
时间。以独立提交隔离此线，公共 ABI 与 SDK 无新增分配。

[Pumpkin 契约](../contracts/pumpkin_identity.md) 记录持久库发布与恢复、安装域和对象
代际。账户 ID 稳定，吊销记录保留。首次采用随机登记凭据，人工密码、POSIX 投影和
提供真实的文件所有权均待专项接入。既有 Apache-2.0 摘要实现用于凭据校验和快照校验，
未引入第三方库。

## 本轮证据

测试运行在 arm64 macOS，使用 Python 3.12.15、Apple Clang 21.0.0 和独立目标编译器
`x86_64-elf-g++ 16.2.0`。

```sh
python3 tests/pumpkin_host.py --target-cxx x86_64-elf-g++ --output build/pumpkin_p0/host
python3 tests/pumpkin_host.py --sanitize --output build/pumpkin_p0/sanitized
```

宿主普通和 ASan/UBSan 各通过七组场景。包含明确空库配置、独立 SHA-256 校验值、
正确与错误认证、授权交集、退出会话和轮换、超时与回收、持久吊销、恢复时双种提交
结果、账户与连接配额。存储重启在新服务实例使用同一测试存储执行。客体磁盘与端点
未运行。目标对象以无 C++ 运行库头、禁异常和 RTTI 的选项编译成功，最终客体链接未运行。
本轮工件路径及 SHA-256：

| 工件 | SHA-256 |
| --- | --- |
| `build/pumpkin_p0/host/pumpkin_core_host` | `863f89d5d094b12cb89223df5ed075b05b8105785e2f66692f77e2f03df45b0f` |
| `build/pumpkin_p0/host/account_store.o` | `4cb78c3cb4da88b2efc61557c94795ee487a764c850c45f3cf5a748999a12418` |
| `build/pumpkin_p0/host/service_core.o` | `82587cb00117b9e1adc2db61c6cecb94de2fed73865dec0931090b8974ccf5b5` |
| `build/pumpkin_p0/sanitized/pumpkin_core_host` | `015558426de0d492653ba553642a0c6d46fed321f3fc262632998cc78829640c` |

编译器栈用量记录在 `build/pumpkin_p0/host/*.su`。启动、写入及 SHA-256 各帧
为静态报告，未来客体适配器需合计服务调用链和实际配置。当前没有可启动的 Pumpkin
工具，因此 xsh/dash 客体入口验收均未运行。现有 ABI 一致性检查通过。

## 交接

冻结隔离测试 profile 的受信启动链、IPC 协议与实际时钟/熵适配器。选择并验证服务私有
持久化后端的原子性、故障矩阵与回滚边界，随后加入独立 guest 客户端。Mobius 只在
客户端入口与保密输入路径验证后接入。
