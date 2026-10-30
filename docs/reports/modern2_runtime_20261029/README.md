# Modern Platform Phase 2：运行时阻塞探针

2026-10-29，独立`codex/modern2-runtime-probes`，基于fetch后的upstream
`aaec2e9d8ffe61ce1d523cd56852d36cde3edd07`。PR #17已合入；
[PR快照](pr_snapshot.json)确认PR #18–#21仍draft/open且reviews/threads为空，
#21 HEAD为`c152f7f93fb11291eb019d572219c2b4d69743a9`。
[所有登记工作区快照](workspaces.json)保留旧分支/HEAD/修改状态；没有重置或修改旧工作区。

本分支交付新客体观测及[Web平台接续](web_platform.md)、
[Python系统/可信文件设计](python_system_semantics.md)，不实现未登记ABI。
网络审查交接由[PR #22](https://github.com/Xiao-John/XylophoneOS/pull/22)交付，
PX4-A接口认领由[PR #23](https://github.com/Xiao-John/XylophoneOS/pull/23)交付；
它们均未自行批准或合并，不能当作可调用能力。

## 真实新运行

系统build **8ac129a963b75031**，镜像SHA256
`f5f5186f5d19358a6793d185b0d335c214275955e661eec8e49669a5f67fcd01`。
重新交叉构建QuickJS ELF SHA256
`b3d51732c2e6a3df104b67759b86aeb7ffbdb014619fcb8e19db87bf49cbdcba`。
普通/线程SDK、运行库/工具、源码manifest、完整命令、实际strip后ELF、工作盘和串口
绑定[qualification.json](qualification.json)与[guest/report.json](guest/report.json)。
新夹具不沿用PR21旧通过；系统与ELF实际在本分支重新构建。

| 能力层 | 本轮实际观察 | 状态边界 |
|---|---|---|
| 真实系统能力 | 普通ELF装载/退出、异常返回后的继续执行与资源回收；内核/libc无改动 | 每次均回到free=130279/tasks=2/completions=0，每个JS进程回收415页；不是全量Qt/线程/故障包重验 |
| 解释器语言 | buffer视图/复制、Promise job、顶层await/export单模块和错误后重跑 | 受限QuickJS语言探针通过；不是V8/JIT/OS映射或线程证明 |
| Web平台 | 原module import缺宿主loader；document/EventTarget/Worker/WebAssembly/location不存在 | 六个明确失败；全局清单还显示fetch/URL/crypto/crossOriginIsolated不存在 |
| 共享语言对象 | SharedArrayBuffer和Atomics名称存在 | 仅类型观察；未验线程共享、Atomics等待、Worker或cross-origin-isolation，不能冒称可用安全Web共享内存 |
| 应用兼容性 | 固定原Code/LocalPilot调用点进一步分解，Python原始依赖探针脚本单独提供 | Chromium/V8、Electron/Code工作台、原LocalPilot Core/API仍BLOCKED/NOT_RUN |
| 正式发行资格 | 本地专用镜像与探针 | NOT_RUN；没有Release、macOS包修改或安全浏览器声明 |

14项`harness_status=PASSED`含预期兼容失败；不能汇总成“Web11/11通过”。
QuickJS上游及PR21显式适配保留原归属；本分支复用同两处补丁并重新编译，
没有删掉Atomics/栈/内存/错误检查，不伪装Linux。

## 复现与输入

来源锁与45份固定公开文件校验在[source_audit.json](source_audit.json)。本轮没有完整
Chromium/Electron/Code checkout；保留固定审计版本，不声称其适合当前产品发行。
QuickJS官方源包2025-09-13-2及其SHA在该回执versions.quickjs；完整SDK树仍为
本地前轮已验证输入，再次绑定实际manifest和所有使用库，不伪称重建了GNU运行库。
builder/runner由PR21演进，增加排空后Promise状态/值检查及pending/rejection/异步断言负控制，新增probe与runner明确在本分支；Apache/上游MIT许可材料保留。

```sh
python3 scripts/modern_apps_build_js.py \
  --output build/modern2_runtime/NEW_QUICKJS \
  --source ../XylophoneOS-modern-app-phase1/build/modern_apps/sources/quickjs-2025-09-13 \
  --sdk ../XylophoneOS-modern-app-phase1/build/modern_apps/threading_sdk \
  --cpp-runtime ../XylophoneOS-dash-c1-c3/build/threading_sdk/cpp/lib
python3 scripts/build.py --output-dir build/modern2_runtime/NEW_SYSTEM
QEMU=/absolute/path/to/qemu-system-x86_64 \
python3 tests/modern2_runtime_guest.py \
  --image build/modern2_runtime/NEW_SYSTEM/xos.img \
  --js-elf build/modern2_runtime/NEW_QUICKJS/js_probe.elf \
  --output build/modern2_runtime/NEW_GUEST
```

客体runner和builder都拒绝覆盖既有output；每次重新复制输入并应用当前补丁，绑定实际runner和builder SHA，
不会以旧缓存代码冒充当前来源/补丁。不可覆盖本冻结资格。完整新镜像资格只属于新运行；旧Qt、FB、N1等仍属各自冻结输入。
没有改变内核/SDK/libc/Qt或应用，故未泛跑无关旧回归或压力测试。

`iterations/`保留首次未主动quiet boot demos的原日志和结果；该轮背景demo输出很多，
后续显式调用既有`demo quiet`再取基线。未修改系统行为来改善结果。
许可材料/ABI/文档/空白检查单列validation；不是逐成员静态产品发行审核。
大镜像/真实ELF/SDK/专用FAT盘留在忽略build目录，不上传私有源码或执行产物。

## 后续仍须保持的门槛

N2继续BLOCKED于PR18审查合入与实际授权桥接，真实Ethernet→ARP→IP→TCP→HTTP及
Aurora接续未运行；HTTPS须独立验证CA/链/主机名/时间/随机数，不能关闭验证。
PX4-A实施仍等待登记合入，高地址页表生命周期与V8低4GiB要求都没有被提案“解决”。
Python静态扩展是独立能力；pypdf/subprocess/select/fcntl、可信owner/path/权限必须逐项
真实完成；原API1.0/身份/Operator/UNKNOWN为后续独立应用验收，不可用import替代。
