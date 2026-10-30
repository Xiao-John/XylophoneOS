# N2最小真实验收设计

状态：**设计，全部客体项目NOT_RUN / BLOCKED**。不填写假结果或代用镜像。
每次新组合必须保存自己的源码/补丁/工具/SDK/ELF/系统镜像/工作盘/夹具SHA256、
完整QEMU argv、QEMU版本及拓扑；禁止把旧N1/B1 report的结果换绑到新输入。
原始失败、完整串口、抓包、截图与资源样本都保留；修复测试器产生新的结果，不覆盖旧失败。

## D1–D3：只有登记合入后才实施和执行

| Gate | 实际刺激与必须观察到的结果 | 必要计数/失败回执 |
|---|---|---|
| D1.1 权利 | 无grant、逐right最小子集、不合法supervisor/child、非法request先拒绝；浏览器和普通进程无原始帧/reset权 | 调用者生命周期身份、grant主体、拒绝码；拒绝前后无新TX/DMA或队列副作用 |
| D1.2 代际 | 两进程串用token拒绝；close/reset/reopen/exec/exit/PID复用后旧token永不重指；fork不继承设备权利 | 代际/handle计数、进程/线程/等待对象前后值；代际耗尽注入按冻结规则fail closed |
| D1.3 活体撤销 | owner在真实WAIT中，授权者撤销使其醒来并失权；无权者撤销失败，未知结果不冒称未执行 | wake原因、单调deadline、撤销到失效顺序；服务与授权者退出的状态转移 |
| D2.1 数据 | 实际NIC TX/RX 14和1514字节、非法13/1515、跨页/无效/只读地址、短RX重试；不截断、不重复入队 | 完整帧摘要、队列入/出与pending/owned计数；授权检查前不访问payload；copy失败原子性 |
| D2.2 有界资源 | TX满、RX溢出、每步分配失败、初始化失败/无卡；成功reset与close/owner退出 | DMA分配/回收/quarantine分别计数，RX/TX owned和pending，free pages/tasks/threads/completions/等待对象；预期丢帧须显式计数 |
| D2.3 DMA失败 | 真实设备关闭/reset确认超时注入；冻结提交，旧引用失效；仍可能被DMA写的页保留 | 失败前后隔离页数与不可重分配证明；不得为了精确回收强行free活跃DMA；在途TX按UNKNOWN |
| D3.1 等待 | RX/TX/失败/撤销事件与deadline前后交错；检查与挂起同临界区；无活动时真实阻塞 | 唤醒原因/期限、任务等待状态、IRQ与完成计数；有界测试中没有丢唤醒和空闲循环，绝对CPU/长压另验 |
| D3.2 生命周期 | 网络服务正常关闭、kill/fault/exec、授权者退出，客户在途和后续调用可观察故障；下一合法owner可按契约打开 | token失效、reset/quarantine、等待对象和端点引用归属；不将重连或在途事务结果自动算成功 |
| D3.3 同组合回归 | 网络机制活跃/失败后，文件read/write/sync、隔离fault、线程/退出、Qt像素与输入、shell救援 | 所有程序自己的ELF/SDK与镜像绑定，前后资源；xsh/dash适用入口分别真实执行，不可执行则明确原因 |

这些gate必须由真实客体ELF调用已登记公共接口；宿主单元测试、内核pre-run诊断和断言源码
不能替代。每项结果分别记录PASS/FAIL/NOT_RUN，D1–D3通过才把桥接当作可用前置。

## N2A–N2D：从lwIP到实际Aurora画面

1. **N2A最小协议路径**：用户态单event loop的lwIP2.2.1接已验桥接，真实绑定monotonic、
   random_bytes、`sys_check_timeouts`。先用显式IPv4/掩码/gateway/MTU和numeric host，
   通过真实ARP问答、IPv4校验/目的地、TCP握手/双向数据/关闭。无DHCP/DNS依赖即可完成首个HTTP目标；
   DNS、DHCP和IPv6仍独立NOT_RUN，不为简化关闭输入长度/校验和/来源检查。
2. **N2B客户端生命期**：session身份与配额、连接代际、短send/read、pbuf引用、超时/取消/close、
   远端RST/FIN、服务故障逐项验。发送已入队和对端已确认分别记录；不把socket空成功作为进度。
3. **N2C受控HTTP**：先Content-Length成功响应，再分段、chunked、redirect、slow、truncated、
   RST/超时/重传与服务失败。客体发出的唯一request_nonce、宿主处理该请求后新生成的response_nonce、
   响应长度和SHA256在客体/宿主记录一致。响应不能从共享盘或离线文件提供；无卡/断路时同请求必须失败。
4. **N2D Aurora**：真实HTTP响应字节经既有browser_http解析，再通过有界network provider进入
   原Gumbo/liteHTML/QPainter流程，保留内容/资源限制。真实地址栏导航产生请求；fresh response_nonce
   在页面可见，客体解析/渲染所用body摘要与N2C一致。保存同run的QMP截图与内容断言、输入/退出/错误恢复。
   普通浏览器不取得原始NIC权利；网络内容不能借file路径/provider获取本地读写或执行能力。

原B1明确拒绝HTTP/HTTPS，不能只取消scheme拒绝而沿用本地provider的路径信任假设。
初期可只允许显式受控源和正文内资源预算；每次重定向重新解析scheme/host/port与授权范围，
跨源资源、file降级、凭据/令牌转发必须拒绝或按独立已冻结规则处理，不能默认“同一网页”。
DOM、JavaScript、Worker、WASM、来源隔离完整平台仍未提供，liteHTML成功不等于现代WebView。

## 因果证据绑定

同一独立run生成一个目录，至少含以下相互校验的数据；文件名是未来接续建议，并非本轮产物。

| 证据 | 必须绑定/核对 |
|---|---|
| `run.json` | 真实源commit/tree+dirty manifest、工具/SDK/ELF/镜像/盘哈希、完整QEMU argv、NIC MAC/MTU、backend/捕获点、服务配置、run ID、开始结束时间 |
| `serial.log` | 网络服务认证身份、guest request_nonce及目标、ARP/连接状态、HTTP response_nonce/字节数/SHA256、parser/provider消费摘要和退出资源；日志不能包含真实凭据 |
| `traffic.pcap` | 在QEMU虚拟以太网边界抓全双向帧；EtherType ARP/IPv4、MAC/IP/port、ARP映射、TCP SYN/SYN-ACK/ACK和序号、HTTP请求/重组响应/FIN或RST；保存丢包计数和snaplen |
| `host_requests.jsonl` | 宿主接到请求的时间/peer/path/request_nonce，处理时新生成response_nonce，实际发出正文/线缆HTTP的字节数和摘要；nonce不可预先放入guest可读response文件 |
| `guest_response.bin` | 实际客体收取的响应字节导出；与PCAP TCP重组、宿主发送记录比较。HTTP wire摘要与dechunk后的body摘要分开，不能因传输编码不同误判 |
| `scanout.png` | 来自该run客体QMP，显示新的response_nonce；同时保存截图摘要、采集时间、provider body摘要与内容断言；截图单独不能证明联网 |
| `resources.json` | 各动作前后free pages/tasks/threads/completions/handles/waits、DMA owned/quarantined/pbuf/PCB/客户端数；成功回收与隔离保留分别报告 |

网络拓扑优先使用单独QEMU user-net连受控宿主loopback服务，不修改宿主代理/TUN/路由、
Clash Verge或远程连接配置。实际可达性仍须客体验证，10.0.2.2并非仅写进配置就算可达。
若backend有NAT/SLIRP，PCAP中的guest四元组与宿主看到的peer并不相同，必须用run ID、nonce、
捕获点与明确NAT拓扑关联，不能要求二者地址相等，也不能拿宿主peer日志单独证明客体来源。

反证必须同run或同绑定组合：移除NIC/禁用服务、使用旧challenge、截断正文/错误长度、分段重排/重传、
错误目标或超时，分别看到真实失败；不得调用宿主网络库代替guest协议栈、把HTTP文件拷进盘、
或把QEMU socket backend的封装TCP误认成guest TCP。成功链与失败链都保留完整原始证据。

## HTTPS独立安全门

N2C/D的HTTP成功不解锁HTTPS资格。独立验证CA来源/更新、完整链与主机名、有效时间、熵、
握手/关闭及短收错误；错域名、过期、未生效、不可信CA、缺链与随机数/时钟失败均须拒绝。
保留默认验证，不用insecure context、不取消安全边界、不静默降到HTTP。TLS失败时UI和调用者
收到真实错误与结果状态，不能显示缓存页冒充新响应成功。
