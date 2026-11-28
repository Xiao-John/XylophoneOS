# fddca1b7 — Issue 125 bounded joins and target thread CPU clocks

2026-11-28。基线 `344655c3f2279a10c62fce5ea039c741aa6172f1`，独立分支
`codex/issue-125-threads-20261128`。解决 Issue #125 / PL-0014 的实际运行时缺口。
发布的 glibc preview-3 仅作为开发环境，未覆盖或重绑其冻结 SDK/镜像。

## 实现与接口

`sys44` 旧第三参数零保留无限 join，新增显式 32 字节 v1 options 指针提供
try 和绝对单调 deadline。查询、独占 join 权、输出 pin、到期释放与结果消费都
在既有内核等待生命周期中仲裁，不靠用户态轮询退出标志。
超时不消费结果、不写用户输出，并释放 join 权，使之后 join/detach 可重试。
两个运行库的 REALTIME 转换先读单调时间再读墙钟，原生提前 timeout 后按原绝对
墙钟期限重新取样；到期仍用零 deadline 原子领取已完成结果，其它错误不重试。

`sys41` 第二参数 mode 1 使用独立 56 字节 v1 target CPU 结构，读取同进程
完整 TID 的实际 user/system CPU 时间与原有分辨率。活的 detached 线程也可
查询；线程结束即失效，不因保留 join 结果而延长 CPU clock 生命周期。
未动 sys89 v1 的 72 字节布局与调用线程含义，没有占新 syscall 或复用保留位。

默认 glibc 和独立 threaded newlib 的 try/timed join、目标 CPU clock 均实现。
glibc 私有 clock ID 为 `-(TID+1)`，超出 `1..INT_MAX-1` 真实返回 `EOVERFLOW`。
newlib 保留 unsigned-long `clockid_t`、正时钟常量和专属运行库隔离，不引入新的
newlib 私有结构耦合。两个运行库的 clock ID 不跨运行库传递。

旧内核 dispatch 前的统一参数门拒绝这些非零扩展参数，新的 try/timed join
不会落入旧阻塞 join。真实旧镜像验证 join 为 `EINVAL`、目标 clock 为 `ENOTSUP`，
输出未变；普通 join 继续成功。ABI 细节见[线程契约](../contracts/threading.md#有界-join-与目标线程-cpu-时钟issue-125)。

修改范围包括共享线程 ABI/SDK wrapper、内核线程 dispatch/reaper 超时处理、
两个运行库的 join/clock、三类 SDK 清单、活测试与相关契约/账本。
`docs/state.md` 按当前纪律留给整体合并者更新。

## 实际构建与客体验证

全部目标构建与 QEMU 验证均在 `xos-sdk-glibc-preview-3` 开发 shell 中执行。
工具版本及实际输入 SHA-256 见[输入回执](../reports/issue125_join_clock_20261128/inputs.json)。
下面是仓库根目录下的实际命令形式；源归档与旧基线目录用显式参数传入。

```sh
python3 scripts/build_glibc_sdk.py --archive "$XOS_GLIBC_ARCHIVE" \
  --output build/issue125_glibc_final --jobs 4
python3 scripts/build_threading_newlib.py --archive "$XOS_NEWLIB_ARCHIVE" \
  --output "$XOS_THREADED_NEWLIB_BUILD" --jobs 2
# XOS_THREADED_NEWLIB_PREFIX 是上述输出中的 prefix 子目录。
python3 scripts/build_threading_sdk.py --newlib-prefix "$XOS_THREADED_NEWLIB_PREFIX" \
  --output build/issue125_legacy_sdk_final --logs-dir build/issue125_legacy_sdk_final_logs
python3 scripts/build.py --output-dir build/issue125_system_final --quiet-demos-on-launch
python3 tests/thread_join_clock_guest.py \
  --system-build build/issue125_system_final --glibc-build build/issue125_glibc_final \
  --legacy-sdk build/issue125_legacy_sdk_final --old-system-build "$XOS_OLD_SYSTEM_BUILD" \
  --output build/issue125_guest_final --repetitions 3
python3 tests/glibc_static_guest.py --system-build build/issue125_system_final \
  --glibc-build build/issue125_glibc_final --suite threads --repetitions 1 \
  --output build/issue125_thread_regression_final
XOS_QMP_TRANSPORT=pipe python3 tests/glibc_g1_bridge_guest.py \
  --system-build build/issue125_system_final --identity-build build/issue125_glibc_final \
  --scheduling-build build/issue125_glibc_final --signal-build build/issue125_glibc_final \
  --output build/issue125_bridge_final
```

实际 guest 全部通过：glibc 三轮、合法 threaded newlib 三轮、旧内核兼容一轮，
七次应用退出均为零，每次资源恢复到各自基线。新系统 build ID 为
`ebaea6ff03805bad`，ISO SHA-256 为
`fd74929bb27140cbafba6654d3c7e825e245c1507474918acbb02b93c4a0eae2`。
新系统资源基线为 `129692 / 3 / 1`；旧基线为 `129693 / 3 / 1`。

glibc 的真实单线程 fork 子进程不能查询父线程 CPU；每种运行库均覆盖非阻塞、
绝对期限、到期后重试、竞争 join/detach、CPU 忙/睡眠差异、退出未 join、
八次槽重用和 detached 生命周期。原 glibc threads 四个场景通过，包括 TLS、
主线程退出、16 轮 detached 回收及阻塞 stdout 的有界退出。
G1 桥接四轮通过；对象从完成 SDK 的归档中逐字节比对后链接，没有伪造旧 G1 报告。

### 线程 newlib 来源

公开源码归档 SHA-256：
`6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`。
真实前缀构建回执 SHA-256：
`70192d8da9e5d511d28f5ea046034b7afe30bd27692770b6751657ce3349bcbc`；
其 build ID 为 `b26d1ef0824937f837476c31196c41bfb384337abad74a93e355d363b36522e1`。
该前缀启用了 retargetable locking，141 个产物由原始回执绑定。
本分支由它重建独立线程 SDK，1331 个产物；没有冒用 preview-2 的单线程 libc。

## 宿主门槛、已知失败与边界

真实 glibc wrapper 的 UBSan 边界检查通过，覆盖期限转换/溢出、输出不变、最大
可表示 clock ID、不可用 CPU 计数及旧阻塞调用路径。原 CPU 记账模型和真实
newlib 时钟 wrapper 检查通过，并增加 unsigned-long 目标 clock 验证。
原 host fixture 的 feature 开关与抽取函数依赖同步修复；不是通过改预期隐藏错误。
两套实际 join wrapper 还分别覆盖确定性的两次取样间抢占、提前原生 timeout
后重试、最终零期限检查与旧内核 EINVAL 单次拒绝；UBSan 均通过。
docs/ABI 一致性保持 79 个已分配 syscall，无新增号。

```sh
python3 tests/thread_join_clock_host.py
python3 tests/cpu_time_host_test.py
python3 tests/threading_clock_host.py
GIT_DIR="$XOS_GIT_DIR" GIT_WORK_TREE="$XOS_GIT_WORK_TREE" \
  python3 tests/docs_consistency.py
python3 tests/abi_doc_consistency.py
python3 scripts/verify_evidence_index.py \
  docs/reports/issue125_join_clock_20261128/manifest.json
python3 tests/check_public_evidence_paths.py --index --base origin/main
```

前五项在 SDK shell 执行，映射后的 worktree 元数据目录通过两个 Git 参数传入；
后两项在宿主 checkout 检查交付文件；前五项的成功输出保存在派生报告中。

独立复核发现初版 wall-first 转换会在两个 syscall 间被抢占后延长绝对期限：
wall=10 秒、absolute=11 秒，恢复时 mono=102 秒，却生成 103 秒期限。
实际 wrapper 的确定性注入复现了该错误；修复采样顺序和 early-timeout 重试后，
复核者再次独立运行 glibc 与 legacy 的 host 用例通过。此前通过的客体报告仅留作
本地诊断历史；最终两套 SDK 和包含新源码身份的系统镜像都重新构建，并重新运行
下面记录的全部客体矩阵，没有把旧结果迁移到新字节。

诊断阶段两次 guest 失败分别暴露本基线不支持 POSIX nanosleep，以及进入线程
profile 后 fork 按契约拒绝；修正的是测试的调度辅助手段与执行顺序，运行时
限制没有放宽。G1 最初缺 names 模块链接依赖，随后完整对象组验证；环境拒绝
默认 Unix QMP socket 后，使用现有 pipe transport 跑通。文档 gate 首次在 SDK
shell 中无法解析宿主 worktree 的绝对 gitdir；仅对该命令显式指定映射后的
`GIT_DIR` / `GIT_WORK_TREE` 后成功，没有修改仓库元数据。失败均未计入通过数。

不宣称异步取消、CPU 时间 timer、跨进程 CPU 查询、SMP、动态/共享运行库资格，
也不改变旧普通单线程 SDK 的 pthread 限制。已发布 SDK 的字节未改，本 PR 是
新源码与新构建资格；未来发行需成套构建相应 SDK/镜像。

交付门：暂存文件公开路径检查为 `PUBLIC_READY`（36/36，无 findings），
本专项平铺清单 7/7 哈希通过。额外运行全库 `tests/report_manifest_check.py`
仍失败：17 条既有报告格式/路径错误，与原始 `344655c3` 基线的失败数组逐项相同；
本次新报告目录明确列为 compliant，冻结历史报告未修改。该全库门不宣称通过。

最小公开派生证据与平铺索引见[报告目录](../reports/issue125_join_clock_20261128/README.md)。
