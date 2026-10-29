# 0081 FB1/FB2 应用故障包与离线定位

2026-10-29，`codex/fb2-offline-symbols` 基于本地 FB0 `be1c21f`（PR #15 尚未合入
`main`）。当时用户要求完成 FB1/FB2 且暂不提交 PR，故先保留本地结果。

## 行为与文件

- xsh 增加 `diag <程序> [参数...]`。装载器新增独立 `spawn_file_diagnosed_receipt`，
  在真实加载所用的同一个只读句柄上流式SHA-256，加载失败回执清零；原有
  `spawn_options` 布局和普通启动路径保持不变。新增SDK清单能力声明，无新内核ABI。
- wait 单一消费者先输出真实结果，fault才生成FB0 v1四文件包。RDRAND失败、quota、
  mkdir/open/短写/close/sync/rename失败均不输出保存成功；写入内容后sync，暂存
  manifest、sync、rename为最终manifest再sync。中间失败可能留partial目录；最终sync
  失败时结果未知，不能推定文件不存在或持久化。
- `scripts/fb2_bind_symbols.py` 用objcopy剥离带符号ELF并与运行ELF逐字节比对，再生成
  两者摘要绑定；`scripts/fb2_symbolize.py` 校验包布局、字段/版本、UTF-8/大小/摘要、
  绑定、ELF与执行段，再对已校验的符号文件快照调用addr2line。错误或缺失符号、坏包
  和无法解析均返回失败；不会按名称猜测。哈希不是签名，也不证明报告来源可信。
- 新增共享用户态SHA-256（从自研FB0夹具及xypm代码适配，Apache-2.0）、客体报告
  writer、独立诊断API、宿主工具、客体/宿主夹具和[使用说明](../implementation/fb12_fault_bundle.md)。
  未修改内核、syscall登记或生产文件服务协议。输出存在FAT工作盘，不自动上传。

## 实际验收

环境：GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2、
Clang 19、Python 3.12.14。构建使用私人子目录，正常系统 build `32fe73250f191e04`；
完整来源/ELF/SDK/工具哈希、报告样本和原始串口见[冻结证据](../reports/fb12_20261029/README.md)。

- 真实客体：正常退出不生成报告；除零vector 0、非法指令vector 6和page fault vector 14
  生成报告；前两种的导出报告确认address=null，取消为killed且不生成故障包。
- 真实客体page fault：回收计数恢复，报告通过正常sync并重启后逐文件字节不变；
  导出后校验，匹配真实运行ELF和带符号ELF，定位到 `fault_test.cpp:14`。原路径替换后
  原报告的ELF摘要不变。
- 真实客体：禁用RDRAND、16包配额、满FAT32盘和QEMU块写入EIO均保留原fault结果并
  不报告保存成功；配额与EIO测试核对已有用户文件不被破坏。
- 宿主writer替身：成功/正数短写、零写、close失败、首次sync失败、rename失败、
  最终sync失败和随机数失败；所有失败均不打印saved。此为边界注入，不代替客体。
- 宿主解析器：实际绑定成功，拒绝错误/缺失符号、伪造绑定、超限、无效UTF-8、
  重复/额外字段、内容篡改、链接和可执行段外地址。
- 同正常系统原有E04进程13组与E05文件8组回归；文档与ABI一致性另行检查。
  `docs_consistency.py` 通过448个本地链接、66个syscall及73份历史来源；
  `abi_doc_consistency.py` 通过。冻结证据21个文件、构建659项输入及218项产物的
  SHA-256逐项核对通过；直接用冻结样本调用定位CLI成功。Python语法检查与
  `git diff --check` 通过。

最初E04测试未挂盘的维护阻断、FB0测试中未触发的块错误及串口竞态保留在FB0报告；
本组早期demo夹具按旧startup版本返回91而非42，改用真实hello后重跑，失败记录留在
  本组`attempts/`。旧混杂构建日志不是最终证据；最终构建和回归使用新建的独立目录。
最终14组客体/导出检查、E04 13组、E05 8组和两组宿主定向检查均通过。

## 复现

```sh
source /workspace/xos-env/activate
cd /workspace/XylophoneOS
export FB12_SYSTEM=/workspace/XylophoneOS/build/fb12/final_20261029e
export FB12_ACCEPTANCE=/workspace/XylophoneOS/build/fb12/acceptance_final_20261029e
python3 scripts/build.py --output-dir build/fb12/final_20261029e
python3 tests/fb12_acceptance.py
python3 tests/fb12_regression.py
clang++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include \
  tests/fixtures/fb12/writer_failures.cpp -o build/fb12/writer_failures_final_e
build/fb12/writer_failures_final_e
python3 tests/fb2_symbolize_test.py
python3 tests/docs_consistency.py --output-dir /workspace/xos-env/logs/fb12-docs
python3 tests/abi_doc_consistency.py --output-dir /workspace/xos-env/logs/fb12-docs
```

测试创建专用临时工作盘并使用QEMU，不操作宿主分区。重建前须确认目录不被其他工作
占用；不要清理其他人的build/盘。每次运行ID不同，不能将新结果改绑旧样本摘要。

## 边界与接续

FB1/2通过范围仅限xsh直接启动并等待的文件ELF、page fault/#UD/除零及已列出场景。
FAT共享命名空间中的16包/2 MiB配额检查不具备跨进程原子性；没有UID权限隔离，
故障包不提供保密或认证。日志/argv/环境、全局收集、后台/孙进程、寄存器/栈快照、
真实硬件、任意断电/扇区撕裂和全量smoke/长期压力未验。FB3/FB4未实施。

后续用户要求建PR时，已确认FB0经PR #15合入主线，合入内容与验收基线一致；本组
提交移至该主线之后。dash没有FB1客体验收：`diag`是xsh内建入口，dash孙进程不在
其收集范围；FB2脚本在宿主运行，不适用客体Shell双验收。宪法C27为后续适用的系统内
工具规定尽可能分别经xsh和dash验收，不改写本组或历史证据。并发配额和更广泛设备
故障仍待补足；FB3/4按需要另行实施。
