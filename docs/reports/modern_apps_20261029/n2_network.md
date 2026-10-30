# N2 网络接续：真实门槛与本轮成果

2026-10-29。本轮**没有完成客体TCP/HTTP闭环**，N2为 **BLOCKED**。
维护者尚未审查/合入PR #18；本轮没有自批、自合并、占用私有syscall号或实现未获登记的公共设备入口。

## 当前实际状态

冻结[远端快照](pr_snapshot.json)与[工作区快照](workspaces.json)：upstream main仍为
`39083f9968d84b5679c86a74a6c8394033c0d915`。PR #18/#19/#20均Draft/open/unmerged，review列表为空。
原网络ABI、N1、Aurora、Qt及GPU工作区保留；新增分支从main独立建立，没有重写这些实现。

| 项目 | 真实状态 | 本轮范围 |
|---|---|---|
| [PR #18](https://github.com/Xiao-John/XylophoneOS/pull/18) | 接口提案；112仅在未合入分支claimed | 未把它当可调用接口；上游ABI仍未登记该具体分配 |
| [PR #20](https://github.com/Xiao-John/XylophoneOS/pull/20) | N1真实Ethernet/IRQ/DMA的原冻结结果 | 未重新构建或借用旧测试作为新组合资格；本轮无驱动改动 |
| lwIP2.2.1 | 已锁定`77dcd25a72509eb83f72b033d219b1d40cd8eb95`，PR #20仅静态准备 | 客体协议栈/服务NOT_RUN；未把其archive称为TCP可用 |
| [PR #19](https://github.com/Xiao-John/XylophoneOS/pull/19) | 离线liteHTML/Aurora与独立HTTP解析器的原资格 | 本轮未改浏览器、Qt、解析器或视觉库；没有浏览器联网成功 |
| 本轮HTTP宿主夹具 | PASSED，5种受控响应通过宿主loopback验证 | 仅HOST_FIXTURE_ONLY；不算客体TCP、DNS、HTTP或渲染资格 |
| 真实客体→宿主TCP/HTTP | BLOCKED | 不用离线网页文件、宿主浏览器或内核TCP替代 |
| HTTPS | NOT_RUN | 不禁用证书校验；本轮没有TLS安全联网声明 |

## 维护者可审查的实施接续边界

PR #18的ABI登记明确规定：先合入claimed登记，再同步共享头/dispatch/SDK/服务/manifest及验收。
这不是本轮临时增加的批准流程，也不能由“文档写了claimed”代替。用户本轮同样要求先审查并登记。

登记前可以准备源码审计、夹具和用户态探针；登记后才进入以下公共机制实施：

1. 冻结64字节request、INFO与grant布局、数值错误、right/event位及复制失败原子性。普通/线程SDK与两个manifest由登记负责人统一修改；不得各线抢号。
2. supervisor仅对其拥有且未启动child受控授予TX/RX/WAIT/RESET子集；right=0撤销。认证进程生命周期身份，不按路径/名字/自报PID授权，不重新解释spawn-only的syscall28。
3. 单一网络服务owner、generation token、不继承/不扩大委派；验证主体/right后才访问payload。跨进程泄漏token、PID复用、旧句柄全部拒绝。
4. 内核独占DMA，用户只copy完整14–1514字节帧；RX/TX各16descriptor的队列满、短缓冲保帧、溢出与非法版本/地址/长度必须真实报错。不给用户BAR、物理地址或任意DMA。
5. IRQ只记录完成并唤醒；事件检查/挂起在同一临界区，绝对单调deadline且单次最多30秒。撤销、退出、关闭、设备失败都可观察；禁止空闲持续轮询替代阻塞等待。
6. reset先冻结提交、真实停DMA再回收；失败则quarantine仍可能被写的页。在途TX为UNKNOWN，不能宣称未发出或已被远端接收。owner故障/exec/close使旧token失效；重启策略在用户态。
7. 网络服务使用受保护IPC，冻结客户端连接身份、配额、短send、partial-read、close/超时/断线与服务退出语义；设备入口不是POSIX socket。只有必要性成立才另做协议/ABI登记，不引入浏览器专属内核接口。

以上为实施输入与验收清单，不是已分配的共享头/错误常量，也不是本轮的实现声明。

## N2实际验收顺序

| Gate | 客体必须产生的证据 | 本轮 |
|---|---|---|
| D1 权利 | 未授予拒绝、最小rights、跨进程token、撤销/exec/退出、PID/token不重指 | BLOCKED |
| D2 DMA/队列 | 真NIC RX/TX、边界帧、队列满/溢出、短RX不截断、分配失败、reset/quarantine | BLOCKED；N1旧结果不替代新服务资格 |
| D3 等待/故障 | IRQ/deadline竞态、撤销唤醒、服务崩溃、无卡/IO错误；精确资源回收 | BLOCKED |
| N2A 协议 | 在客体lwIP接Ethernet/ARP/IPv4/UDP/TCP；真实monotonic与random绑定 | NOT_RUN |
| N2B 配置/DNS | 显式IP/route/MTU/DNS，ARP更新、UDP回包、DNS成功/失败/超时；DHCP若启用另验 | NOT_RUN |
| N2C TCP/HTTP | 客体主动连受控宿主、随机challenge及字节哈希一致、分段/短收/关闭/重传/超时 | BLOCKED |
| N2D Aurora | 浏览器真实发HTTP请求→响应字节→现有解析器→liteHTML/QPainter；截图与内容断言 | BLOCKED |
| N2E 回归 | 文件/sync、隔离、线程、Qt/显示、网络服务故障后继续运行；当前组合独立重验 | NOT_RUN |
| TLS独立阶段 | CA来源/更新、链/主机名、时间有效期、随机数、缺失/过期/错误主机/不可信证书拒绝 | NOT_RUN |

## 可直接复用的受控HTTP夹具

源码：[宿主服务](../../../scripts/modern_apps_http_fixture.py)、[夹具验收](../../../tests/modern_apps_http_fixture.py)。
服务仅监听127.0.0.1；固定测试QEMU user-net将来可用10.0.2.2访问宿主，实际路由仍须N2验证。
每次生成新challenge token和正文hash，记录真实请求时间、peer、路径、字节数。
提供普通Content-Length、chunked、redirect、slow、truncated五种路径。生成的HTML含真实样式和链接，供既有liteHTML消费者使用。

```sh
python3 scripts/modern_apps_http_fixture.py --output build/modern_apps/n2-live-fixture --port 18080
```

本轮测试完成后宿主服务已停止。夹具自测5项PASSED只证明夹具本身，不能证明请求来自XOS。
未来验收必须同时绑定QEMU拓扑、客体调用日志、宿主新challenge请求日志、响应字节哈希和浏览器内容；
不能把响应文件拷进客体当成联网结果。HTTPS夹具/证书链/CA/时间/RNG专项尚未实施。

## 可并行开工的下一轮

- **维护者/网络设备负责人**：先完成PR #18审查/必要登记，再独占公共头、dispatch、SDK、授权与回收实施；结合PR #20的原驱动，不重写N1。
- **网络服务负责人**：协议/对象/生命周期设计与夹具可先准备；真实lwIP接卡和TCP/HTTP依赖已验device bridge，不能抢先提供伪socket。
- **内存/线程负责人**：VMA/保护/共享对象的缺口探针和预登记、V8实际预算；不由应用团队临时放宽内核。
- **Python/文件负责人**：独立静态扩展候选、select/subprocess、可信文件身份与权限设计；原LocalPilot源码/安全门保持。
- **Web/Code负责人**：固定源码与调用矩阵、DOM/Worker/WASM/Web Crypto探针集；工作台运行等待真正Web引擎。Aurora界面与Qt库保持原所有权。

上述为责任建议，不代表已派出Agent或已占用其工作区。本轮只有一个实施者和私有build。
