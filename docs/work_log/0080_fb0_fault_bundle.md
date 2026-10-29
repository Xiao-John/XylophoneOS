# 0080 FB0 应用故障包勘查与格式冻结

2026-10-29，基线 `4322caf`，分支 `codex/fb0-scout`。用户要求完成FB0；本组交付
[FB0 v1格式与接口约定](../implementation/fb0_fault_bundle_contract.md)、受限客体/宿主
探针和[冻结证据](../reports/fb0_20261029/README.md)。FB1–FB4未实施。

## 勘查结论

- `sys_process_wait` 按真实父PID匹配完成记录，成功复制后消费；无效用户缓冲不消费。
  xsh `result_line` 是直接前台子进程的现有消费者。新增报告应在这个单一消费者接入，
  不能让另一个进程再次wait或靠名称获取任意PID的结果。
- `spawn_file_diagnosed_impl` 打开只读句柄，传给 `spawn_reader` 反复seek/read并在
  完成映射后close，再start；close失败不启动子任务。探针在实际loader `Client::open`
  的测试型链接包装中读取同一打开句柄全部ELF并SHA-256，seek回零后将该句柄交回
  未修改的loader；待装载ELF与宿主摘要一致，随后子进程真实启动并故障退出。
  该包装仅用于探针，不是已交付生产哈希回执；读锁阻止替换由独立数据句柄测试。
- 异常状态含vector、page fault CR2和RIP，不包含完整寄存器/TID。客体验证无效缓冲
  wait=-2、有效wait=0、vector=14、address=1048576、RIP=1073742015，再次wait=-1；
  故障后另一个demo正常退出42。无新增内核ABI。
- 同一数据句柄完整读取、试图replace得到busy=-5，再从该句柄读回相同768字节；
  宿主摘要 `f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363`。
  额外对探针自身ELF执行客体流式SHA-256并与宿主比对。SHA实现是测试夹具，从
  自研 `xypm_native.hpp` 摘取并保留Apache-2.0，不是新增生产库。
- 独立FAT满盘回归返回保存失败并保留原文件。正常系统通过QEMU blkdebug在实际块写入
  注入一次EIO，编辑器得到save error=-7并保留缓冲、提示结果可能未知；其后客户端
  ping=-7。没有把未触发注入时的sync成功算作故障通过。
- 独立故障注入系统的files服务在处理特定stat请求时触发#UD并退出；在途stat最终
  would_block=-8，随后ping因发送端点失效返回io=-7，监督终端stats仍可响应。
  现有客户端最多8192次recv/yield，这是次数上限，不是保证的墙钟截止，也不能推定
  之前的请求未执行。服务不会因此自动恢复。故障点只存在隔离系统的测试补丁。
- 宿主替身对未修改的 `Client::call` 验证8192次无应答返回-8、发送失败返回-7；这项
  仅是宿主边界证据，不能代替上面的客体服务退出实验。

## 格式和职责

v1固定report/image/context/manifest四个UTF-8 JSON对象、必需字段、严格上限、unknown、
摘要、版本与单一wait权限；运行ID基于已验证随机接口并检查失败，不由PID或名称授权。
默认不收集日志、argv、环境、内存或寄存器；包可读不等于可信/签名。保存失败/UNKNOWN、
正常sync重启与任意断电安全分开。暂未申请新syscall、文件服务op或预留号。
具体格式以实现文档为准，FB1仍须实现编码、发布、边界检查和失败夹具。

## 实际验证

环境为 `/workspace/xos-env/activate`：GCC/G++ 16.2.0、Binutils 2.47.20260726、
NASM 3.02、QEMU 11.1.2、Clang 19；Python 3.12.14。正常build `6c2e83dfaa2737bb`；
故障注入build `084024c841126499`。结果、工具与源码/镜像/ELF哈希见冻结证据：

| 检查 | 结果与边界 |
|---|---|
| `make build` | 通过；正常源码/SDK/镜像绑定正常build |
| `python3 tests/fb0_probe.py` | 5组通过：同句柄读取、客体ELF摘要、装载器同句柄摘要与wait、故障后正常程序、真实块写EIO |
| `python3 tests/full_disk_smoke.py` | 1组通过，实际满FAT16盘的失败保存与旧数据保留 |
| `python3 docs/reports/fb0_20261029/e04_fixture.txt` | E04 13组通过；包装原测试仅为提供独立FAT盘 |
| `python3 tests/file_smoke.py` | E05 8组通过，独立FAT盘 |
| 编译并运行 `tests/fixtures/fb0/file_client_failure.cpp` | 宿主无应答/发送失败两种边界通过 |
| `python3 tests/fb0_service_exit.py ...` | 独立注入系统2组通过：服务退出请求返回、监督终端仍可响应 |
| `python3 tests/docs_consistency.py --output-dir /workspace/xos-env/logs/fb0-docs` | 通过：439个本地链接、66个已分配syscall及73份历史来源 |
| `python3 tests/abi_doc_consistency.py --output-dir /workspace/xos-env/logs/fb0-docs` | 当前ABI速查与源码一致 |
| 证据文件SHA-256复核与 `git diff --cached --check` | 15个冻结文件摘要一致，暂存差异无空白错误 |

无盘原E04运行因xsh维护恢复要求阻断而失败；供盘后重跑通过。第一次blkdebug尝试
没有触发实际写入，sync返回成功；修正为写操作后才通过。一次串口接收竞态只等到
数字前缀导致断言失败；修正为等待完整`-7`行后通过。相关失败保留在证据`attempts/`。
未运行全量smoke、真实硬件、任意掉电、生产包写入/解析及寄存器/栈快照。

复现隔离服务退出实验（以下目标目录须为新的空目录，不覆盖已有工作）：

```sh
source /workspace/xos-env/activate
cd /workspace/XylophoneOS
make build
python3 tests/fb0_probe.py
mkdir /tmp/xos-fb0-service-fixture
git archive 4322caf | tar -x -C /tmp/xos-fb0-service-fixture
patch -p1 -d /tmp/xos-fb0-service-fixture < tests/fixtures/fb0/service_fault.patch
(cd /tmp/xos-fb0-service-fixture && python3 scripts/build.py)
python3 tests/fb0_service_exit.py --image /tmp/xos-fb0-service-fixture/build/xos.img \
  --probe build/fb0/probe.elf --injected-source /tmp/xos-fb0-service-fixture/src/user/services/files.cpp
clang++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include \
  tests/fixtures/fb0/file_client_failure.cpp src/user/sdk/file_client.cpp src/user/sdk/text.cpp \
  -o build/fb0/file_client_failure
build/fb0/file_client_failure
```

测试仅操作新建的临时盘。若 `/tmp/xos-fb0-service-fixture` 已存在，选择另一个新目录；
不得覆盖或清理其他工作。重建后build ID取决于实际输入；不能将新结果改绑旧冻结回执。

## 接续

本组结束后不占用公共build。下一组FB1先登记职责和独立构建目录，实现绑定同一reader的
生产流式摘要及回执、xsh单一wait接入与有界保存；新增功能须在实际客体验证短读、
close/sync失败、满盘/服务死亡、正常/异常退出、权限和资源回收。当前未添加生产
实现、全局服务、用户态core、日志收集或新ABI；不因FB0通过宣称FB1已交付。
