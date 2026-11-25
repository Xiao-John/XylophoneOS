# 70ac29fe — browser native HTTP provider

2026-11-25。源基线 `08f3e13ead01c0d8d7d535e9f85d7d94510c2b20`。
本模块叠加于N2原生网络服务和N3客户端/HTTP分支，单独PR审阅。

## 实现与审阅

- `--network-service-pid` 显式启用HTTP，认证服务两端IPC peer PID。
  默认仍加载本地 `/web`，连接、权限和设备全部由N2服务持有。
- 数字IPv4 HTTP及2xx完整响应；现行服务只授权10.0.2.2。远程CSS/BMP绑定
  文档host/port和回调base，同源规则阻止资源读取本地文件。浏览器不跟随重定向。
- 每次导航首次网络请求起共享3秒单调deadline、17次请求、2MiB响应读取预算。
  先预留字节，成功才退还未用容量。原有32KiB HTML、8KiB CSS、8图像和有界
  BMP/布局限制继续生效。
- 初始解析/布局结束即关闭IPC，绘制/resize不发起远程请求。加载候选视图，
  错误保留原页面/历史/滚动。Home、历史和书签使用明确file/http地址。
- 独立审阅后加固：资源校验显式锚定文档来源；延迟链接回调捕获绝对URL，
  旧视图替换前清空导航和标题回调，避免相对URL被后续页面重新解释。
- 内容读取和缓冲区分配纳入候选页面异常处理，错误诊断比较避免再分配临时字符串。
- builder编译真实HTTP解析和transport，检查SDK网络头与当前源码一致，回执
  绑定所有新增头/源码及provider预算。保持Qt既有C++17构建，无newlib私有接口。

没有修改glibc移植代码、内核syscall、设备授权、冻结报告或全局状态摘要。

## 已运行

环境为Linux x86-64、GCC/G++14.2.0、Python3.12.14。

```sh
python3 tests/browser_network_policy.py
CXX=g++ ASAN_OPTIONS=detect_leaks=0 python3 tests/browser_http_test.py
python3 -m py_compile src/ports/aurora_browser/build.py tests/aurora_browser_http_guest.py
python3 tests/aurora_browser_http_guest.py --help
```

- 生产policy/parser的C++17严格编译和ASan/UBSan通过：9组来源检查、8组非法
  主机、URL长度/格式、截止时间溢出/到期、请求/字节预算及重置。
  新测试将sanitizer诊断设为fatal，发现问题即失败。
- 既有HTTP解析器 **208检查 + 4096畸形向量 PASS**，以GCC显式运行。
  首次使用默认clang++因编译器缺失未运行，随后用现有GCC重放。
- Python语法、guest runner参数入口、diff格式检查通过；新runner实际guest流程待验。
- 公开路径检查 **PUBLIC_READY，10/10文件**。
- 独立审阅覆盖资源来源、候选页面/历史回退、会话关闭、预算与builder输入，
  生产policy测试由另一位审阅者独立重放通过。
- ASan的LeakSanitizer受本环境ptrace限制关闭，泄漏检测 **NOT_RUN**。

## 初次提交时的客体缺口和接手

**目标Qt编译/链接和真实浏览器验收尚未运行。** 环境缺固定x86_64-elf
GCC/G++16.2.0、Binutils2.47.20260726、NASM3.02、QEMU11.1.2、匹配冻结SDK、
Qt6.8.3目标构建与开发头。系统预检实际在NASM检查停止。

GUI线程同步执行网络等待，全导航共享网络deadline。GUI响应、等待中取消、CPU布局
绝对耗时需单独验证和后续异步设计。DNS/DHCP/TLS/HTTPS、JavaScript、通用网站、
POSIX socket/glibc适配和WebKit仍按既有阶段推进。

后续成员将N2、N3及本PR放入同一源码树，用源码锁指定lwIP归档构建系统，重建
匹配native/threading SDK、Qt及浏览器，保存system/SDK/Qt/ELF/输入回执。
按[浏览器契约](../contracts/aurora_browser.md)执行新鲜HTTP/CSS guest runner：
校验真实GET/Host/close、fresh body SHA-256、同run截图、三次退出资源恢复及net-stop。
截图仅验证尺寸并留证，视觉内容还需独立核验。继续补充：

1. 同源BMP、跨源/本地资源拒绝、404/畸形/截断响应、超时和服务死亡。
2. HTTP与本地页面导航、重载、Back/Forward、tab切换、错误恢复和单进程预算重置。
3. 原有local interactive/negative/lifecycle及no-display套件，用新ELF重跑。
4. 多应用网络与资源压力、调度/设备IRQ/reset、重启和独占设备退出。

缺少环境时runner保留not_run并写明预检错误；取得匹配guest证据后再更新资格。

## 组合补验（2026-11-25）

- 以锁定的 Qt 6.8.3 和目标线程 SDK 重建真实 Aurora。当前 SDK 已实现
  `fchmod`，移除 Qt 私有旧 stub 后通过目标链接。
- `b097514b230c15e2` 通过本地 interactive 10 项、negative 18 项、
  lifecycle 7 项和 no-display 3 项。已在 guest 复现串口消息拆分和尚未呈现的
  帧导致的验收误判，并令测试等待完整计数和实际画面。N2 服务 PID 行改成单次
  写入，避免被进程启动输出切断。
- `b185cefce6cca571` 使用同一浏览器 ELF 通过增强 HTTP 客体 9 项，
  含新鲜 HTML/CSS/BMP 字节、样式和位图像素、跨源及远程引用本地 CSS 拒绝、
  HTTP 404 和截断、三轮正常退出、失败用例退场及服务关闭后的资源恢复。
- 普通宿主规则测试以及 HTTP 解析器 208 项和 4096 个畸形向量通过。
  图形的网络等待响应性、远程交互、服务故障和长时间并发保留独立门禁。
  组合回执在本地 `build/pr143-147-browser` 与 `build/pr147-http-extra`。
