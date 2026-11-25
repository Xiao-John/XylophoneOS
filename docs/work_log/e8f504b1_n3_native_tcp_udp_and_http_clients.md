# N3 原生TCP/UDP与受控HTTP客户端

2026-11-25。堆叠在N2分支`codex/net-n2-service-20261125`的本地实现
`c7b4a36859a36f648c2f6903f3157f1cbd486e30`上；对应N2 Draft PR #145。
本组完成实现和可重放的宿主验证，固定工具链与完整客体验收由后续成员补充。

## 实现与选择

`src/user/include/xos/net_transport.hpp`提供C++17、PID固定、单调用方串行使用的
原生客户端。TCP open等待建立、read/write返回短计数；UDP保留原子报文、空报文和
容量不足的队头重试。所有操作沿用调用方绝对deadline，只重试已确认would_block；
交付后超时关闭会话，不自动重放。close/cancel分别有序关闭/终止，服务侧回收连接。
SDK随既有头文件收据复制，无新增syscall、wire字段、errno、POSIX FD或newlib私有类型。

`src/ports/browser_http/transport.*`复用现有严格HTTP解析器，通过真实N2 TCP执行
数字IPv4 GET。短写循环、Content-Length、EOF、额外尾字节、截断、错误清理和
最多5次同源重定向均采用一个总期限。调用方得到HTTP状态、完整body范围和最终URL；
max_redirects=0返回第一条完整响应。默认静态网络授权仍只允许10.0.2.2非零端口。
头部采用增量线性扫描，只有完整头和EOF时解析，避免一字节分片反复扫描全部头部。
限额继续为16KiB头与1MiB body，调用方固定缓冲区可进一步限制。

审计进一步收紧`net_service_client.hpp`的逐操作响应形状：information32字节、
open/status无payload且有效状态位、send/control无多余payload/flags、receive有效
容量/EOF；保留真实failed与buffer_too_small所需容量。收到回复后重新检查deadline，
覆盖调度停顿期间跨期的已交付请求；损坏或迟到回复回收两个endpoint。

glibc PR #142涉及独立glibc端口/构建/测试，本组不修改其文件。探针使用原生crt0与
libxos，不链接libc，不涉及pthread/TLS/VM/装载器改动。Aurora界面与资源策略由独立
浏览器PR接入同一fetch API；本PR只交付传输库和其真实客体探针。

## 验证与审计

宿主环境GCC14.2.0、Python3.12.14；C++17，严格Wall/Wextra/Werror/Wconversion/Wshadow。

- `python3 tests/net_transport_host.py --output build/net_transport_normal`通过。
- `ASAN_OPTIONS=detect_leaks=0 python3 tests/net_transport_host.py --sanitize --output build/net_transport_sanitized`
  通过；ASan+UBSan使用`-fno-sanitize-recover=all`，无诊断。当前ptrace环境的LSan未运行。
- 原生SDK六组场景覆盖空UDP、容量不足保留并重读、connecting/status推进、短写、
  would_block后新sequence、已接受请求丢回复/迟到回复不重放、TCP数据+EOF、错误
  sequence/object、冲突状态、16种成功回复多余payload/flags，以及双endpoint清理。
- 生产HTTP覆盖一字节头分片、二进制NUL、201状态、短读写、截断、尾字节、容量上限、
  chunked拒绝、同源重定向/最终URL、跨地址/端口拒绝、重定向额度、0次返回和IPv4规范。
- 相同runner严格编译真实native guest probe，并将probe、HTTP、SDK syscall/text和
  freestanding memory用实际用户链接脚本做宿主链接，无libc依赖；记录相对源码哈希。
  这项检查使用宿主工具链，固定XOS工具链/CRT实际运行仍待补。
- 继续运行N2基础SDK测试、ABI表检查和当前文档链接/登记检查；Python语法与差异空白通过。
  当前文档链接1016处、ABI登记78项通过；完整docs_consistency历史来源阶段的按需
  对象获取缺口沿用N2交接。
- 实际运行native probe builder，停在`Missing x86_64-elf-g++`；客体runner的缺输入
  路径写出status=not_run及缺失manifest原因，该负向预检通过，未启动客体。

客体runner审计修复了首次NIC映射导致资源基线变化、restart重复匹配旧ready日志、
缺输入未写not_run报告、失败路径宿主socket/thread未清理，以及dash显式exec不兼容
原生CRT的问题。现在先运行net-probe预热，再取基线；每次启动使用新输出偏移；
预检与执行失败均保留原因和已尝试交换；宿主线程有取消/关闭和有界join。dash脚本
走普通spawn并传递返回码，保留现有原生CRT权限边界。

## 完整客体验收缺口

固定x86_64-elf GCC16.2.0/Binutils2.47、NASM3.02、QEMU11.1和匹配冻结SDK缺失。
N2-enabled完整镜像、native probe目标链接、真实IPC/IRQ/DMA、xsh/dash的HTTP/UDP
新鲜挑战和关闭/重启/回收均为not_run。构建/客体runner已准备，按以下命令补验：

```sh
XOS_LWIP_SOURCE_ARCHIVE=<locked_archive> python3 scripts/build.py --output-dir build/net_n3_system
python3 scripts/build_net_transport_probe.py --sdk build/net_n3_system/sdk --output build/net_n3_probe
python3 tests/net_transport_guest.py --system build/net_n3_system --payload build/net_n3_probe/net_transport_probe.elf --output build/net_n3_guest
```

可选追加`--dash <matched_dash_elf> --dash-sha256 <hash>`，同时核验dash普通启动路径。
runner校验系统source/artifact、SDK完整树、ELF与builder收据，然后使用运行时生成的
32位hex nonce和32字节随机挑战，要求HTTP201/UDP精确字节、双向关闭、错误PID拒绝、
关闭端口失败、服务重启和资源恢复。完整N2多应用并发、撤销、reply阻塞500ms、idle60s、
kill/exec/fault、丢包重排、NIC reset失败quarantine仍需专项补充。DNS/DHCP/TLS、
IPv6/监听、POSIX socket和浏览器综合资格属于后续模块/阶段。
