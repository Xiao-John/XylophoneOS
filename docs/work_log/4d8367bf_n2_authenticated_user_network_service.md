# N2 authenticated user network service

2026-11-25；基线main `08f3e13ead01c0d8d7d535e9f85d7d94510c2b20`。
当前PR交付实现与可重放验证，完整客体验收由具备固定环境的成员补充。

## 范围和实现

先在`net_service_v2.md`与ABI登记冻结独立net2命名空间，再实现共享线布局、认证IPC
客户端、生产service_core、轮转IPC循环、服务内真实lwIP后端和可选锁源构建。
服务独占设备与栈，四个普通会话加独立controller额度；认证PID与连接handle双重归属，
地址白名单在PCB分配前检查；有限回复、短写、UDP消息边界、TCP窗口背压、取消/撤销、
对端退出、空闲回收、绝对期限和真实错误贯穿实现。栈继续使用上游2.2.1 NO_SYS。

默认`net-start 41`启动v2。v1只有controller stop兼容；旧ARP诊断保留，旧lwIP raw
探针须显式`net-start 41 raw`，其runner和说明已迁移。这个诊断profile需要所有活动
进程受信，不能用作N2隔离验收。N2运行只依赖已存在sys4/5、46/47、63、81、84–86、112。
没有更改syscall、pthread、TLS、VM、ELF或glibc候选代码。

`XOS_LWIP_SOURCE_ARCHIVE`必须匹配既有source_lock；构建离线验证后提取，归档散列、
开启状态参与系统build_id，并把全量提取源码清单绑定到`net_lwip_inputs.json`。
归档未提供时明确拒绝v2，raw/probe继续可用。lwIP BSD声明加入SDK许可证材料。
服务专属arch/cc使用标准整数/尺寸头、避开不需要的unistd/ctype运行库耦合。

## 实际验证

- `python3 tests/net_client_host.py`：通过；核验双端peer、错误服务身份、响应sequence、
  发送前期限、交付后超时只发送一次、重连sequence重置、时钟错误。
- `python3 tests/net_service_link.py --archive <locked_archive>`：宿主GCC的真实服务+
  真实上游lwIP freestanding链接检查；保留目标ABI/链接脚本和严格警告，使用临时GAS
  入口代替不可用的NASM。链接后的镜像71312字节，小于131072字节限制。
  此检查没有调用客体syscall，不把宿主GCC当作固定XOS工具链。
- `XOS_LWIP_SOURCE_ARCHIVE=<locked_archive> python3 tests/net_service_host.py`：
  20/20真实lwIP包交互场景通过；相同命令加`--sanitize`并设置
  `ASAN_OPTIONS=detect_leaks=0`后20/20 ASan+UBSan通过，使用
  `-fno-sanitize-recover=all`使诊断直接失败。当前执行器的ptrace环境不支持LSan。
  场景覆盖认证、重放、额度、撤销、二进制/空UDP、TCP握手/短写/环回绕/FIN/RST、
  期限、重传、帧预算、故障，以及接收SYN-ACK前和回调内跨越期限两条路径。
  runner同时严格编译真实IPC循环及XOS_NET_STACK开启/关闭入口，并保存源码散列收据。
- 审计据实际失败修复三处配置/时序问题：UDP PCB额度显式配置为8；x86-64的
  lwIP分配对齐设为8；待建立TCP在收帧前过期，并在连接回调内复核绝对期限，
  中止PCB后返回`ERR_ABRT`，避免过期握手复活和回调所有权错误。
- `python3 tests/abi_doc_consistency.py`通过。文档检查的当前链接/登记检查分别
  检查1013处链接与78项登记，通过；完整`tests/docs_consistency.py`历史来源阶段
  因部分克隆按需获取旧对象长时间等待而中断，仍需联网完整clone补验。
- Python语法检查与自有源码`git diff --check`通过；`licenses/lwip.txt`逐字保留上游
  COPYING及其末尾空行，唯一空白提示为这处上游原样文本。

## 待补客体验收

本环境缺固定x86_64-elf GCC16.2.0/Binutils2.47、NASM3.02、QEMU11.1及匹配冻结SDK。
完整系统构建预检停在NASM不存在；新镜像、客体IPC/IRQ/真实网卡、QEMU字节挑战、
xsh/dash并发/退出/restart、全资源回基线均未运行。旧N1/raw结果保留原范围。

补验命令起点：

```sh
XOS_LWIP_SOURCE_ARCHIVE=<locked_archive> python3 scripts/build.py --output-dir build/net_n2_system
python3 tests/virtio_net_guest.py --system build/net_n2_system
python3 tests/lwip_tcp_guest.py --system build/net_n2_system --payload <rebuilt_probe> --output build/net_n2_raw
```

后续N3提供TCP/UDP便利SDK和真实HTTP挑战runner，基于此PR堆叠，浏览器接入独立PR。
N2客体还需补：4应用隔离、PID撤销与拒绝重连、错误格式/重放、reply阻塞500ms与idle
60秒清理、kill/exec/fault、服务stop/restart、NIC失效与reset失败quarantine。
DNS/DHCP/TLS、POSIX socket/errno/FD映射、IPv6/监听、多核/IOMMU属于后续阶段。
