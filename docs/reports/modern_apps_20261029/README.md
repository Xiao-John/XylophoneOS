# 现代应用兼容平台第一阶段：冻结证据

2026-10-29。主线输入upstream `39083f9`，独立分支`codex/modern-app-phase1`。
最终系统build **a538733bd3b8e43f**；不是新的XOS Release。

**N2客体TCP/HTTP尚未完成：BLOCKED于PR #18的维护者审查与登记合入。**
完整Chromium、LocalPilot Core/API、Code - OSS均BLOCKED，完整产品构建/运行及HTTPS尚未验收。
本轮交付真实客体能力/失败探针，不提供三个模拟应用。

## 独立报告

- [Chromium / V8 / 独立JavaScript](chromium_compatibility.md)，[12行实际调用点矩阵](chromium_matrix.csv)。
- [LocalPilot](localpilot_compatibility.md)，[11行实际调用点矩阵](localpilot_matrix.csv)。
- [Code - OSS](code_oss_compatibility.md)，[12行实际调用点矩阵](code_oss_matrix.csv)。
- [N2门槛、受控HTTP夹具与后续派工建议](n2_network.md)。

## 实际状态

[qualification.json](qualification.json)绑定实际产物、独立探针源码SHA及状态。
`harness_status=PASSED`只代表11项测试器断言正确复现行为，**包含预期的兼容失败**。

| 项目 | 结果与限制 |
|---|---|
| QuickJS交叉编译/链接 | PASSED；官方2025-09-13-2，2处显式源适配，真实XOS ELF |
| 客体语言/边界/错误 | 语言、异常、未处理Promise拒绝、循环中断、失败后重跑、内存/栈预算返回和回收正确 |
| Code实际上游script | FAILED：URL不存在；测试器正确记录错误退出 |
| LocalPilot实际React bundle | HOST构建PASSED；XOS模块FAILED于document不存在；Promise拒绝被计为错误 |
| Python依赖 | 16项实际观察：4 PASSED、12 FAILED；逐项见[运行回执](guest/report.json)和[串口](guest/serial.log.gz) |
| Python通过项 | 两线程/锁、SQLite3.54.1提交重开/完整性、defusedxml实体拒绝、32字节熵读取 |
| Python失败项 | pypdf、Pillow、psutil、socket/SSL/subprocess、可信文件打开，以及原Core模块依赖链；没有降级绕过 |
| 原生依赖编译 | psutil单元FAILED；Pillow正确构建宏下单翻译单元PASSED，链接/codec/静态集成NOT_RUN |
| SDK前置 | 7项FAILED；V8配置头解析另有PASSED；均不是完整上游构建 |
| 宿主HTTP夹具 | 5项PASSED，明确HOST_LOOPBACK_ONLY；无客体网络成功 |
| 资源 | 所有最终客体操作后均回到`free=130290 tasks=2 completions=0`；不是绝对峰值或长压力资格 |

最终JS进程每次回收415页；Python探针进程回收8999页。JS内存输出是执行后的样本。
中途256KiB解释器栈导致vector14，XOS杀进程并回收498页；该失败单列保存，不能删掉后宣称首轮全部通过。
本轮实际受影响回归为同镜像中异常/中断/资源限额后的再次执行、Shell继续可用、原生线程/锁、文件/SQLite/XML及资源回收。
无内核/公共ABI/libc/Qt/驱动改动，因此未重复旧全量Qt/GPU/N1资格；这些仍仅属于原冻结输入。

## 证据目录与输入

- [source_lock.json](source_lock.json)：实际公共源SHA/URL/逐文件SHA；保留最初错误路径404记录；不是完整checkout。
- [pr_snapshot.json](pr_snapshot.json)、[workspaces.json](workspaces.json)：远端PR与本地所有登记工作区快照；其他Agent工作未改。
- [input_verification.json](input_verification.json)：实际SDK文件与既有C++runtime校验、编译器版本及输入关系。
- [python_dependencies.json](python_dependencies.json)、[localpilot_audit.json](localpilot_audit.json)：包锁与私有源码元数据；不含私有源正文。
- [guest/report.json](guest/report.json)：实际QEMU命令、镜像/ELF/工作盘哈希、逐操作资源与16项兼容观察。
- `inputs/`：系统、普通SDK、线程SDK、CPython构建/stage、C-only早期SDK及许可回执；大JSON无损gzip。
- `sdk/`、`native/`：实际编译命令、状态和原始诊断。
- `build/`：构建/宿主前端/打包原始日志，含失败；`failures/`：失败客体、错误QEMU、早期错误预算/测试器结果。
- `http_fixture/`：宿主夹具配置、原始请求及5项验收；不算N2回执。

ELF、SDK、系统镜像、源码缓存与专用工作盘保存在本worktree忽略的`build/modern_apps/`、`.cache/xos_seed/cpython/`。
[qualification.json](qualification.json)列出实际绝对路径、字节数和SHA256；未覆盖已有发行版。
工作盘是含私有LocalPilot源码的本地测试盘，不提交、不上传；2GiB是盘容量而非应用内存使用。

独立SDK从已有verified newlib生成；C++runtime从旧XOS SDK逐文件核验后导入，没有宣称重建GNU运行库。
SQLite构建时使用补入C++runtime之前的C-only manifest，保存并核验了该原manifest；最终CPython绑定完整线程SDK。
普通SDK和最终系统有独立manifest，不混用资格。许可材料检查PASSED不等于逐成员/静态产品发行许可审查完成。

## 复现入口

以下命令在仓库根执行。已有交叉GCC/LD/NASM、匹配工具运行库和QEMU；不自动升级全局环境。
每次用新的output目录；改变源码、SDK或组合时生成新资格，不能覆盖本目录或复用旧“通过”。

```sh
# 校验并恢复固定公共源、QuickJS与包输入；不运行其中的程序。
python3 scripts/modern_apps_prepare.py

# 原SDK/runtime输入见inputs与本地manifest；build_js参数显式指定实际XOS运行库。
python3 scripts/modern_apps_build_js.py \
  --source build/modern_apps/sources/quickjs-2025-09-13 \
  --sdk build/modern_apps/threading_sdk \
  --cpp-runtime ../XylophoneOS-dash-c1-c3/build/threading_sdk/cpp/lib

python3 scripts/modern_apps_sdk_probe.py \
  --sdk build/modern_apps/threading_sdk --v8 build/modern_apps/sources/v8 \
  --output build/modern_apps/reproduce-sdk
python3 scripts/modern_apps_native_probe.py \
  --sdk build/modern_apps/threading_sdk \
  --python-work .cache/xos_seed/cpython/a8201ed0a683f05afdf3 \
  --output build/modern_apps/reproduce-native

# 仅供拥有该私有仓库的人；源码必须是报告绑定的main SHA。
python3 scripts/modern_apps_localpilot_audit.py \
  --source ../localpilot-source-audit-20261029 --output build/modern_apps/reproduce-lp-audit.json

QEMU=/Users/perry_guo/Documents/ChatGPT/os/runtime/qemu-prefix/Cellar/qemu/11.1.2/bin/qemu-system-x86_64 \
python3 tests/modern_apps_guest.py \
  --python-work .cache/xos_seed/cpython/a8201ed0a683f05afdf3 \
  --localpilot ../localpilot-source-audit-20261029 \
  --image build/modern_apps/final-system/xos.img \
  --output build/modern_apps/reproduce-guest

python3 tests/modern_apps_http_fixture.py --output build/modern_apps/reproduce-http-fixture
```

CPython完整构建实际命令位于`build/python-build-attempt2.log.gz`与`inputs/cpython_build_receipt.json.gz`；
使用报告绑定的CPython3.14.9源包、host build Python、线程SDK、SQLite/zlib receipt。
GNU交叉工具的`as`/`ld`须通过专用COMPILER_PATH绑定，不能落到宿主Apple assembler。
宿主前端构建命令是私有快照`desktop/`内的`npm ci --ignore-scripts`与`npm run build`；
Core wheel用`python3 -m pip wheel --no-deps`，只证明HOST打包。

完整重新构建系统可用`python3 scripts/build.py --output-dir build/modern_apps/NEW-system`；
完整工具命令、ELF链接参数和实际可执行文件哈希均以回执为准。
原公开依赖许可证保留在`licenses/modern_apps/`及源码缓存；没有发布任何产品二进制。
