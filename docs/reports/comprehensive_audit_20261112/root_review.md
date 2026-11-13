# 构建、交付和证据工具专项复核

初审基线：`e6246faf8eefac305a99528f727b1592ee93a5b2`；最终增量基线：
`4c9b6f8feb0667d7169167e406da662be789876c`。日期：2026-11-12。
本文件补充总表中 B01–B06、B14、B16–B17、B23、T01–T03 的实现和验证边界。

## 1. ISO 结构的两个实际错误

ISO 9660 的目录记录具有固定头、标识符和按标识符长度决定的填充。原生成器在偶数
名称长度时遗漏填充；根记录上限又按错误长度计算，允许不能装入单字节记录长度的边界。
本轮修正填充和上限，将最长根名称从 220 调为 219。相同镜像还缺少必须存在的大端
Type M 路径表，本轮补生成并更新 PVD、路径表位置和后续 extent。

`tests/make_iso_names.py` 检查实际生成文件的目录记录长度、零填充、文件名边界、
Type L / Type M 的端序与内容、各文件 extent 和 payload。没有以一份复制的目录生成
算法替代产品实现。新增用例先在旧实现失败；当前输出为 `ISO_NAME_CASES_OK`。

格式依据是 [ECMA-119 第四版](https://www.ecma-international.org/wp-content/uploads/ECMA-119_4th_edition_june_2019.pdf)
的 §6.9.2–3、§9.1.12。本轮没有通过 BIOS/QEMU 启动该镜像；镜像结构通过与启动通过
是不同结论。

## 2. 静态归档读取与来源绑定

基线 newlib、GCC、Qt 三个脚本各自读取 GNU ar，缺少统一的内容长度、尾部和长名称
处理约束；部分路径把成员放进字典，会静默覆盖同名成员。本轮将实际读取集中到
`scripts/archive_member_map.py`。当前实现针对仓库实际 GNU ar 格式，拒绝截断 payload、
残缺头、错误 trailer、非法 size / padding、错误长名称引用和不能唯一映射的重复名称。

三个旧入口继续保留原调用形式，避免重写消费方。Qt 的 retained-object 规则还补了
对象文件与归档 payload 的逐字节比较；存在同名路径但内容不同，不能再标成 object_record。

`verify_manifest` 实现仓库既有 archive provenance 契约的 v1 内容校验：归档 SHA-256、
准确成员集合、源路径与摘要、build id、声明类别和 derived 标志。成功状态仅代表
`content_verified`。它无法证明分类声明本身正确，也不能证明该清单在原构建时生成；
因此没有把 D12 标为完全完成。

验证使用真实 `ar` 生成的归档，14 项 unittest 通过。另与真实 `ar t` 交叉比较了仓库
`libc.a` 的 627 个成员和 `libm.a` 的 426 个成员，名称及顺序一致。后者只证明读取器
能正确列出这些真实归档，**不等于审计过归档内全部函数实现**。

下一步应在 newlib/GCC/Qt 同次重建过程中生成清单并接入验收，而不是给旧推导报告
更换标签或改写冻结哈希。

## 3. libc 审计和缓存

`scripts/libc_audit.py` 原来把 `nm` 输出的 archive/object 标题当作符号，且报告内容仍
沿用早期 E06 的 ENOSYS、固定堆和 TLS 结论。当前修复从实际已定义符号与 SDK manifest
出发，区分 libc、libxos、loader 的符号来源；报告明确只是链接符号清单，不推导运行资格。

`tests/libc_audit_symbols_test.py` 实际编译对象、调用 ar/nm，再运行报告逻辑。1 项集成
回归通过。完整交付 SDK 的审计没有运行，因为所需构建输入不存在。

`scripts/xypm_image.py` 将不可解码的 UTF-8 cache stamp 作为缓存失效处理。真实 helper
重新编译测试通过，避免一次损坏 stamp 使之后的所有操作停在 UnicodeDecodeError。
这项修改只发生在缓存输入边界，没有给下游增加重复防御性检查。

## 4. C++ ABI probe 的输入保护与报告新鲜度

### B16：拒绝输出位置后仍写入输入

原 builder 在检测 output-root 位于 SDK/runtime 内后抛错，但异常报告写入仍使用该
路径；外层 smoke 即使收到 builder 拒绝，也会继续向同一路径写自己的报告。本轮让
两入口共享已有的输出范围检查，在任何报告写入之前拒绝这类参数。没有扩大已存在
的保护范围，也没有加入新的权限系统。

真实 CLI 回归覆盖 SDK 本身、SDK 子目录、runtime 本身、runtime 子目录，对 builder
和 smoke 各测一次；逐文件比较拒绝前后输入，要求没有报告和目录污染。合法外部
输出仍能保存正常的 not_ready 诊断报告。

### B17：非零退出后继续消费旧报告

原 smoke 仅在 builder 返回 0 时检查报告 mtime。未知 feature 会在新报告创建前失败，
这时旧 `partial_not_ready` 报告可能被接受，并导致后续运行旧 guest 用例。

修复只去掉新鲜度判断对返回码 0 的限制。`tests/cpp_abi_output_test.py` 运行实际
builder/smoke 命令，以未知 feature 和预先放置的旧报告验证：最终明确 failed、
report_error 为旧报告、guest_execution 为 not_run。旧实现不能满足该断言，修后通过。

这两项属于输出副作用和证据真实性问题；没有因此宣称目标 C++ ABI 资格已通过。

## 5. 发行待办的源码处理

本轮将 BT-03/BT-05 落到现有 freeze → package → smoke 流程：冻结已构建的
`user_xos_diag.image.elf`，打包前按 system manifest 校验，装到 `/usr/bin/xos-diag`，
同时建立 PATH 已引用的 `/bin`；release smoke 检查目录和诊断程序摘要。

Linux 上不支持的 `cp -c` 已替换为现有标准库 `shutil.copyfile`。旧命令在本机的
失败已经复现，替换没有引入新的复制工具。

交叉复核发现本轮初稿的 hash 检查误用了未导入的 `require`；在交付前已按本脚本
原有风格改为 `p.error`。实际 main 的四条诊断程序预检语句配合真实文件 SHA 和真实
ArgumentParser 验证：正确 hash 添加一个准确的 guest entry；错误 hash 退出 2，
不添加条目。证据列于 `validation_results.json` 的 `release_diagnostic_preflight`。

现有 release SDK binding 测试会在坏 SDK 处提前退出，不能覆盖这个新成功路径。
本轮没有完整构建或执行 package/release smoke，旧已发布镜像和 SDK 未改变；
该待办的最终退出条件仍是下一次完整发行验收。

Qt 修改通知补登记了后加入的第 11 个 qmalloc 补丁，保留历史十补丁统计的原含义。
Python 用法说明补充已知 exec_prefix 提示的含义和如何区分真实导入错误；解释器提示
本身未被消除。二者都是文档和交付材料处理，不计成新的内核运行缺陷。

## 6. bundle 负例修到真正测试声称的对象

`test_parse_rejects_non_elf_tool` 原来只是解析合法文件并检查类型，不能证明 non-ELF
被拒绝。现在修改真实工具 payload 的魔数，并要求明确的非 ELF 错误。

`test_parse_rejects_backslash_name` 原来修改的是 entry offset，遇到的是越界错误，
而非名称字符校验。现在定位准确的名称区，修改名称并检查对应错误。真实 bundle
套件 27 项中 26 通过，1 项因为缺少 idna XPK 跳过；没有把缺少样本改成静默通过。

## 7. 阅读方法和冻结代码

全树路径基线为 5,250 项。代码范围以总报告的 CSV 为准，包括 `.c/.cpp/.cc/.h/.hpp`、
汇编及 include、Python/shell、链接脚本、JavaScript/HTML/CSS、Swift、Make/CMake、
patch/diff 和有关构建输入。CSV 中 `inventory_only` 表示仅盘点，不能作为全文审阅。

冻结报告中的 78 个代码/补丁路径已经复核；其中九个 P4A 快照先与已读当前实现比较，
相同者按字节相等登记，不同者完整阅读差异；另一份 independent audit 与其已读
initial 版本完整对照。CSV 显式记录比较对象与方式，不声称对相同副本重新逐行通读。

旧快照可含旧镜像名、旧 Qt 错误文本或旧 ABI 符号。这些是当时证据的一部分，本轮
没有修改它们。需要当前主干结果时应重建新产物和新报告，不应运行旧脚本后覆盖旧证据。

## 8. 最终结果的解释

最终 unittest 共 256 项：253 通过、0 failure、2 error、1 skip。两项 error 都来自
`package_p0_cases` 缺少 `build/releases/0.0.1-1024`；skip 为缺 idna XPK。没有降低
失败条件，也没有将这些项目移出统计。

最终 Python 语法扫描 430 文件，其中 429 可解析，唯一失败是明确的负例
`tests/fixtures/cpython_py1/syntax_error.py`；27 个 shell 文件的 bash 语法检查通过。
这些检查不证明脚本的全部运行路径正确，bash 语法检查也不是全部 shell 的运行资格。

初始批次直接运行 `unicode_width_consistency.py` 时缺少其必填 archive 参数，退出 2；
本机没有锁定的 newlib 源归档，完整宽度对照未运行。`fb2_symbolize_test.py` 因缺少
同次 guest acceptance report 与绑定 ELF 退出 1，完整符号绑定验收也未运行。这些
前置条件失败保留在汇总中，没有冒充产品源码 bug。browser_http 初次缺默认编译器，
后来明确以宿主 g++ 重跑通过；这只证明宿主解析器行为。

`make build` 实际返回 2，停在 NASM 不存在。固定 cross compiler、QEMU、目标 SDK
和 Qt 构建环境均缺失，因此 BIOS、真实调度、设备、GUI、SDK 重建和完整发行验收
仍为 BLOCKED / NOT_RUN。宿主对象编译、模型、定向语句检查分别记录，不能相互替代。
