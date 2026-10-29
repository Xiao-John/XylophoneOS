# 现代 Web 引擎兼容性报告：第一阶段

2026-10-29。完整 Chromium/Blink/V8 **BLOCKED**；完整构建、content shell、现代网页和不可信内容隔离 **NOT_RUN**。
独立 QuickJS 的真实客体语言/资源探针已有运行证据；它不是 Blink、DOM、WebView 或现代浏览器。
Aurora/liteHTML 保持 PR #19 的离线范围，本轮没有改其 UI、Qt 或内核。

## 固定输入与实际构建范围

[源码锁](source_lock.json)绑定 Chromium **142.0.7444.59** / `4b8153ab58d3c3f4c9f7e4baad9616ecf80db5fa`，
DEPS 对应 V8 **14.2.231.14** / `bb294624702efbb17691b642333f06bf5108e600`。
源码是有哈希的实际文件子集，没有完整 gclient checkout；不能将源文件审计称为 Chromium 构建。
这是固定审计样本，不声明该旧版本适合作为2026年的浏览器发行版本。

该 Chromium 源码的 `tools/clang/scripts/update.py:42–43` 固定
`llvmorg-22-init-8940-g4d4cb757` / subrevision4；本轮没有下载或执行该整套工具链。
实际 XOS 探针用 GCC16.2.0、Binutils2.47.20260726、NASM3.02、newlib4.6及独立线程SDK，
普通 ELF64 静态装载、QEMU11.1.2/TCG/单核/512MiB。具体工具二进制摘要、SDK、ELF、镜像、命令和日志在
[证据入口](README.md)与最终回执；没有用宿主浏览器代执行客体脚本。

## 实际调用点矩阵

完整精确矩阵为 [chromium_matrix.csv](chromium_matrix.csv)，逐行绑定原文件/行号、当前行为、缺口、责任角色和探针。
它覆盖12个已核对调用点，不是完整 Chromium 系统调用闭包，也不据此计算兼容百分比。

| 实际调用点 | XOS 当前行为/缺口 | 建议实现方与验收 |
|---|---|---|
| V8 `platform-posix.cc:170` mmap | 无公共sys/mman.h；内部兼容符号返回ENOSYS | 内存/ABI负责人先设计匿名VMA、对齐、保留/提交、guard、unmap和归属；跨进程拒绝/失败回滚探针 |
| 同文件`:539` mprotect | 没有已验的公共页保护接口 | 内存负责人；W^X、NX、只读写故障、撤销、线程并发及实际执行转移 |
| 同文件`:514` MAP_SHARED | 无共享映射契约 | 内存/IPC负责人；对象权利、只读副本、转交、退出/撤销和失效句柄 |
| 同文件`:1305` pthread_create | 现有1:1子集；每进程4线程、全局32 | 线程/引擎负责人；冻结真实V8线程/栈预算，不能只提高配额冒充可用 |
| Chromium `launch_posix.cc` fork/execve | 普通SDK单线程eager fork；线程profile拒绝fork/exec | 进程/装载负责人；安全启动、受控句柄、故障/取消/等待和精确回收 |
| `message_pump_epoll.cc` epoll_create1/epoll_wait | word/IPC/pipe等待不是epoll | 等待/SDK负责人；有界就绪集、deadline、close/cancel和无丢唤醒 |
| `platform_shared_memory_region_posix.cc` AllocateFileRegion | 文件服务不提供对应共享/封印语义 | 文件/内存/IPC联合；RO转交和所有者生命周期 |
| `native_library_posix.cc:35` dlopen | 仅静态ELF；dlfcn.h缺失 | 装载/运行库；依赖/重定位/TLS/失败闭包；静态探针不能推出动态模块 |
| `credentials.cc` sys_unshare/权利处理 | 无Linux namespace/seccomp后端 | 安全/进程负责人；设计XOS原生broker与权限限制，证明隔离效果；不要求照抄Linux内核 |
| content shell ContentMain | 未构建，没有Ozone/XOS窗口后端 | 引擎/图形负责人；软件Skia→受控surface、输入/事件循环、故障与像素验证；继续复用Aurora Glass |

SDK编译前置探针实际 **FAILED** 于V8未选出XOS OS、sched.h/sys/mman.h、socket、dlfcn、PTY与inotify头缺失。
V8配置头本身能解析 **PASSED**，不等于选出平台或构建引擎。没有把XOS伪装成Linux以绕过检查。
源文件的半套include闭包不作“完整V8构建失败”证据；完整引擎构建保持NOT_RUN。

## 独立 JavaScript 引擎的真实结果

选择官方 QuickJS `2025-09-13-2`（源包 SHA256 `996c6b5018fc955ad4d06426d0e9cb713685a00c825aa5c0418bd53f7df8b0b4`）
作为可独立交付的解释执行探针。原版交叉编译 **FAILED**：分配器声明及非标准 `tm_gmtoff`。
[显式补丁](../../../tests/fixtures/modern_apps/quickjs_xos.patch)只包含XOS malloc头和上游已有的标准时间转换分支选择；
没有伪造时间、分配成功、POSIX成功或平台宏。Atomics/栈检查保留，未定义EMSCRIPTEN来删检查。

真实XOS已观察到 BigInt、可选链/空值合并、TypedArray、Map、Unicode正则、JSON错误及Promise运行。
初版256KiB解释器预算超过128KiB进程栈：递归客体触发vector14，内核杀进程并回收；失败串口保留。
64KiB预算后，递归返回stack overflow，32MiB申请触发16MiB运行时限额，死循环被interrupt预算终止。
最终冻结结果以最终回执为准；脚本也检查未处理Promise拒绝，不能把模块返回Promise/退出0当作前端成功。

这些限制不证明成熟的安全浏览器沙箱。一般恶意脚本、Atomics阻塞、CPU/内存极限压力和漏洞逃逸均NOT_RUN。
所有客体执行与父Shell回收按最终计数报告；当前内存样本不是绝对峰值。

## 阶段判据与下一步

| 阶段 | 本轮状态 | 后续客体必须证明 |
|---|---|---|
| HTML/CSS | 本轮NOT_RUN；PR #19原输入有离线资格 | HTTP响应字节实际进入liteHTML，布局/输入和错误恢复；不换成宿主下载文件 |
| 独立JavaScript | 有真实受限语言探针，最终回执单列 | 更多语言/GC/异常/生命周期专项；不是DOM资格 |
| DOM/CSSOM/事件 | BLOCKED | 真实document、节点变更、layout、事件和来源隔离 |
| 资源加载/网络 | BLOCKED于N2 | 重定向、分块、截断、超时、连接复用、页面/子资源归属 |
| HTTPS/Web APIs | NOT_RUN | TLS链/域名/时间/CA/RNG；Worker、WASM、Fetch、Web Crypto、存储分别验收 |
| 现代网页 | NOT_RUN | 固定页面集、功能断言与失败截图；不能以截图相似取代交互 |
| 不可信内容隔离 | NOT_RUN | renderer/broker最小权利、跨域、跨进程、服务故障与资源回收 |

建议先做VMA/保护的必要性论证与ABI预登记，再评估原生V8平台；`jitless`可另作解释执行配置研究，
仍需VMA/隔离且不能关闭V8 sandbox等校验来争取通过。content shell排在公共机制具备之后。
Firefox/Gecko仅列可比较路线，本轮没有其固定源码/构建/运行证据，也没有成本优劣的实测结论。
