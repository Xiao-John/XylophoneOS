<!-- SPDX-License-Identifier: Apache-2.0 -->
# 使用 P1-A 只读观测与提案回放

普通 XOS 程序可以通过这个接口读取已获授权的进程、服务、资源及选定代次，
导出类型化 JSON，再由宿主工具验证记录下来的提案。整个流程不需要模型。
接口只提供读取；提案校验成功也不会执行动作或获得执行权限。

完整边界见[观测服务契约](../../contracts/observation_service.md)，底层 sys90
见[原生观测契约](../../contracts/native_observation.md)。这对应
[P1-A 计划](../../plans/p0_completion.md)，不表示其他 P1 工作或 P0 最终验收已经完成。

## 选择匹配的 SDK 与内核

使用本次源码构建的 SDK 和内核。公共头包括 `xos/observation.hpp`、
`xos/observation_sources.hpp`、`xos/observation_service_abi.hpp` 和
`xos/observation_abi.hpp`；用户态实现随匹配 SDK 的 `libxos.a` 构建。
普通 SDK 的 provider 使用 `sources::capture` 时还须链接
`libxos_loader.a`，建议将这两个 archive 放在同一 linker group；仅使用 client
不需要 source adapter 的 catalog 依赖。普通 probe 的构建脚本提供了完整范例。
旧发布 SDK 不会因为头文件复制进项目就获得新内核能力。保持同一 libc/profile
的头、启动对象、库和镜像成套，不混用已有 newlib 与 glibc 候选。

在已选择的预览 SDK 开发环境内，从仓库根构建独立输出：

```sh
python3 scripts/build.py --output-dir build/p1_a_system
```

若通过 SDK 的 `xos-sdk` 启动器进入环境，可以将仓库作为 `--workdir`，再执行
上述命令。`build/p1_a_system/sdk` 是该次源码构建的原生 SDK；保留其 manifest
与同次系统镜像。现有应用的编译、装盘入口见[用户态上手](getting_started.md)。

## 普通客户端：验证身份后读取

以下是可嵌入普通 SDK 程序的函数。`expected_pid`、`expected_epoch` 和服务名称
应来自可信 supervisor 或部署配置。名称发现只定位端点；不能用未认证回复替换
预先要求的身份。`deadline_ns` 是当前客体单调时钟域中的绝对纳秒期限，最多
向前五秒。

```cpp
#include <xos/observation.hpp>

xos::observation::status read_process_observation(
    const char* name, xos::u64 expected_pid, xos::u64 expected_epoch,
    xos::u64 deadline_ns) {
    using namespace xos::observation;
    client reader;
    status result = reader.connect(name, expected_pid, expected_epoch);
    if (result != status::ok) return result;

    response sample{};
    result = reader.read(kind::process, deadline_ns, sample);
    if (valid_response(sample)) {
        const status printed = print_json(sample);
        if (printed != status::ok) return printed;
    }
    return result;
}
```

`client` 离开作用域时关闭其端点。读取失败有两种可区分情况：收到的完整失败
回复可以导出带状态、空 `records` 的 JSON；本地期限已过、断链或畸形回复可能
只返回类型化状态而没有有效 envelope，不能把全零 `response` 当成一次成功
观测。记录返回状态，重新核对身份与授权，再决定是否发起新的读取。

需要核对先前观察到的对象时，将预期值传给 `read`：

```cpp
xos::observation::response sample{};
const auto result = reader.read(
    xos::observation::kind::process, deadline_ns, sample,
    expected_object_id, expected_image_generation);
```

非零预期值必须精确匹配；不匹配返回 `stale`，不返回旧数据。不要在旧期限上
反复重试，也不要把重连看作自动恢复授权。

## 提供者：先 attach，再 authorize

提供者由应用显式持有，不会自动成为系统全局服务。最小配置可以只观察自己：

```cpp
#include <xos/observation_sources.hpp>

xos::observation::sources selected_sources{}; // process_target=0: provider self
xos::observation::server observer;
const auto started = observer.initialize(
    xos::observation::sources::capture, &selected_sources);
```

成功后，owner 使用既有 IPC 名称发布／接受接口管理连接，并通过可信控制路径
分发自己的 PID 和 `observer.epoch()`。`selected_sources` 和其引用的 catalog、
Net2 session、已验证 trust store 必须持续存活，并与 `poll` 在同一 owner 中
串行使用。活动 trust 来源通过 `trust_capture_fn` 读取 owner 选择的实际 ready
store；单独配置一个 generation／digest pin 不能返回 `ok` 活动信任状态。

接受到连接并按自己的 allowlist 确认消费方之后，执行：

```cpp
const auto attached = observer.attach(accepted_channel);
if (attached == xos::observation::status::ok) {
    const auto admitted = observer.authorize(
        trusted_reader_pid,
        xos::observation::mask(xos::observation::kind::process) |
            xos::observation::mask(xos::observation::kind::resource),
        8, grant_expires_ns);
    // Check admitted. A failed authorization leaves the attached channel
    // owned by observer; forget(trusted_reader_pid) retires it when desired.
} else {
    // attach did not take ownership; close BOTH accepted endpoints here.
}
```

`accepted_channel` 来自 owner 的真实 IPC accept，`trusted_reader_pid` 是 owner
批准的、与该连接核对过的消费 PID；两者不是远端请求自行声明的字段。
观测传输使用 sys84 generic endpoints，包含 sys86 具名连接创建的同类端点。
sys81 `generic_channel` 不能通过这里的 `query_peer` 认证；底层 sys90 能观察
已持有的 sys81 端点，并不表示观测服务支持使用 sys81 传输。
`attach` 会独立认证两端并取得镜像代次。`authorize` 必须在其后调用；仅附着
不会授予任何读取权限。每个 grant 最多 64 次读取、30 秒有效期。

owner 循环调用 `observer.poll()` 处理已附着连接。它不等待空闲客户端，但
会同步执行 capture；一次 Net2 capture 可以占用剩余请求期限，最长五秒。
四个客户端的 capture 串行执行，不能把 `poll()` 当作立即返回或公平并行的
调度器。自定义 capture 也必须遵守传入期限，不能依赖 owner 强制中断它。

管理生命周期时使用不同操作：

| Owner 操作 | 效果 |
| --- | --- |
| `revoke(pid)` | 撤销该消费方的 grant，保留可观察的 revoked 状态；尚未发送的成功回复会重新检查授权 |
| `forget(pid)` | 关闭该消费方的全部已附着连接，释放其 grant 槽，供后续消费方使用 |
| `authorize(...)` | 对仍获认证的已附着镜像显式重新授予种类、次数和期限；创建新 grant revision |
| `close()` | 关闭全部连接并清除全部 grant |

grant 绑定 PID 和镜像代次；同 PID exec 后的镜像不能继承旧 grant。已经进入
邮箱的旧成功回复仍是历史上被授权的读取，撤销不会擦除已交付的副本。发生断链、
超时或结果未知时，接口不会自动重连、重新采样或执行提案。

## 看懂 scope 与 generation

`observation.source.pid` 是提供者，`caller_pid` 是消费方。`self` 和
`direct_child` 都相对提供者，而非消费方。源适配器只读取 owner 明确配置的
范围，不允许请求者随意填入其他进程 PID。

| 记录 | 可用于核对的事实 | 不能据此推出的能力 |
| --- | --- | --- |
| process | 提供者自身或其直接子进程的 PID、镜像代次、状态、线程数 | 读取无关进程或孙进程 |
| service | 已持有端点的对端 PID、镜像代次和端点可用性 | 任意名称枚举、服务业务健康；`interface_version=1` 仅指观测元数据版本 |
| resource | 提供者或直接子进程的 generic IPC pair／名称用量和 4／2 上限 | 进程树预算、全系统可用资源；`endpoints_used` 数的是 pair |
| runtime | 真实 controller catalog 当前 root ID、sequence、digest | 持久 provisioning 或全局活动运行时 |
| network | 已认证 Net2 session 的真实 peer PID、配置 epoch、模式与配置状态 | 网络连通性、连接目的地授权 |
| trust | owner 选择的实际 ready、已验证 immutable snapshot 的 generation/digest，标记 `loaded_snapshot` | 既有 TLS stream 已切换／撤销信任根、TLS 连通性或全局默认 trust store |

每次读取只有一条独立观测。不同读取之间状态可能改变，不能拼成原子全局快照。
`unavailable` 或记录缺失表示没有该项可用观察，不能推出对象不存在。

活动 trust 必须来自真实 `native_tls::trust_store`：先按独立授权 pin 完成
有界快照加载与校验，再由 bridge 复制 loaded generation 和完整快照摘要。
未选择 store、`ready()==false` 或首次加载失败都不能成为成功活动记录。
旧的 `selection="configured_pin"` 标签会被 v1 schema 拒绝。这里选择的是
provider 当前用于观测的实际 store；既有 TLS stream 的 anchor 副本不会因此
改变，也不代表已经完成握手或网络连通性验证。加载和寿命规则见
[TLS trust store](../../contracts/tls_trust_store.md)。

已经使用 native TLS 的应用可以显式连接
[可选 bridge](../../../src/ports/native_tls/observation.hpp)。以下片段假定
`store` 是 owner 为后续新连接选择的、已经成功 `load`／`load_file` 且 ready
的 `native_tls::trust_store`；在仓库构建中使用该 include 形式需将 `src`
加入头文件搜索路径（`-I src`）：

```cpp
#include <ports/native_tls/observation.hpp>

selected_sources.trust_context = &store;
selected_sources.trust_capture = native_tls::capture_trust_observation;
```

这个 bridge 是 native TLS port 的可选头，不是基础 observation SDK 自动启用
的依赖。不要传入 pin 指针或销毁后的 store；切换 `trust_context`、销毁旧对象
与读取必须由同一 owner 串行执行。未安装 bridge 的普通客户端／提供者仍可使用
其他观测种类，并把 trust 来源明确记为 `unavailable`。

## 保存提案并离线回放

三个文件定义记录格式：

- [observation_v1.schema.json](../../schemas/observation_v1.schema.json)
- [proposal_v1.schema.json](../../schemas/proposal_v1.schema.json)
- [observation_replay_v1.schema.json](../../schemas/observation_replay_v1.schema.json)

回放文件包含原始 observation、记录下来的 proposal、三个版本号、逻辑时间和
显式 policy。policy 列出消费 PID、允许的目标、scope、动作和最大观测年龄。
它描述本次离线评估输入，不证明当前内核仍授权这些对象。保持 source incarnation、
observation ID、target ID/generation 不变，明确记录提案到期时间；不要用当前
宿主时间覆盖原记录的逻辑时间。

先运行仓库中的合成记录示例：

```sh
python3 scripts/observation_replay.py \
  tests/fixtures/observation/self_inspect.json
python3 scripts/observation_replay.py \
  tests/fixtures/observation/unsupported_write.json
python3 tests/observation_replay_test.py \
  --output build/p1_a_replay_host
```

第二条会输出类型化 `unsupported` 并返回 1，这是该 fixture 的预期结果。
这些 fixture 明确是 synthetic，用来验证离线边界，不是 QEMU 运行记录。
验证器使用纯 Python 标准库；上面的输出目录须是新的目录。

| CLI 退出码 | 结果 |
| --- | --- |
| 0 | `accepted_proposal`：记录满足记录中的验证 policy |
| 1 | 类型化拒绝，例如 unauthorized、stale、deadline、quota、unavailable 或 unsupported |
| 2 | 畸形输入或 invalid 结果 |

版本 1 只接受 `inspect`、`diagnose`、`refresh_observation` 这三种提案。
所有结果都带 `execution_authority=false` 和 `automatic_retry=false`。
输出还绑定 canonical input、三个 schema 和 validator 源码的 SHA-256。
同样的记录与验证器字节产生同样的结果；模型输出是已记录的输入，不假设模型
再次生成时会给出相同提案。

## 原生与 transport 的独立检查

以下检查直接验证生产代码，但仍在宿主上替代了内核 trap／时钟等边界：

```sh
python3 tests/observation_native_host.py \
  --sanitize --output build/p1_a_native_host
python3 tests/observation_transport_host.py \
  --sanitize --output build/p1_a_transport_host
```

真实客体的构建与验证入口为：

```sh
python3 scripts/build_observation_probe.py \
  --sdk build/p1_a_system/sdk --output build/p1_a_probe
python3 tests/observation_guest.py \
  --system build/p1_a_system --fixture build/p1_a_probe \
  --output build/p1_a_guest --repeat 3
```

普通客体配置把缺失的网络／trust 来源记录为类型化 `unavailable`。runner 的独立
`--network` 模式只运行读取真实静态 Net2 配置的六源场景；应为该模式选择其
匹配系统／SDK／probe，并使用新的输出目录。它不会运行 DHCP 租约状态转换，
也不会发送应用网络流量或记录报文。两个模式都不代表 runtime ELF 加载、CA
bundle 加载、fork generation 客体验证或默认安装组合已经完成。实际 loaded
trust snapshot 的 bridge 由单独的真实 store 回归核验；其运行环境与结果以
该项记录为准，不能从普通 guest 的 `unavailable` 或合成 JSON 推导已经通过。

先检查各脚本的 `--help`，使用与系统镜像同次构建的 SDK。命令入口本身不是
“已通过”的证据；实际成功、失败、未运行项、所选网络配置和镜像／SDK 身份
以本次 P1-A 交付记录为准。宿主测试通过不能替代 sys90 的真实客体执行，独立
测试镜像通过也不能自动推广成默认安装组合已经验收。
