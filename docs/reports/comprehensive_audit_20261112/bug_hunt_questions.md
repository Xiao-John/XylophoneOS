# XOS 找 bug 题目索引：依据现存记录重建

日期：2026-11-12。核对基线：`e6246faf8eefac305a99528f727b1592ee93a5b2` 及本轮审计工作区；收尾再核对至 `4c9b6f8feb0667d7169167e406da662be789876c`，新增 IPC 提交未补回原题。

**这是一份依据已提交的历史修复日志和现有测试重建的 24 题索引，不是原始比赛题目的全文。**
题目编号由本次整理新增；数个相关历史发现合并为一道操作题，不保留原报告的题号对应关系。
这些问题大多已经修复，适合作为代码阅读、回归检查和故障注入练习，不能视为当前版本仍有
24 个未修 bug。每题给出操作、判断标准、源码和真实测试入口。

## 一、原始材料在哪里，为什么当前拿不到全文

当前仓库的 [`.gitignore`](../../../.gitignore) 排除了 `CONTEST`、`blind_test` 两个根目录。
`git ls-files blind_test CONTEST` 只列出 [pipe_drive.py](../../../blind_test/tools/pipe_drive.py)，
它是记录输出并经 FIFO 驱动程序的工具，没有题目正文。忽略规则解释了这些本地材料为何不随
当前检出交付；它本身不能证明材料曾在所有历史提交或外部位置都不存在。

| 已能确认的原始名称 / 路径 | 可核对的已提交记录 | 当前缺口 |
|---|---|---|
| `CONTEST/bug-hutting-contest-3/found_bug.md` | [0212][L12]：15 项静态/宿主发现 | 原文件未跟踪 |
| `CONTEST/bug-hutting-contest-4/real_bugs.md` | [0213][L13]：3 项代码缺陷、1 项注释问题，另发现同类路径边界问题 | 原文件未跟踪 |
| `CONTEST/bug-hutting-contest-1/found_bug.md`、`CONTEST/bug-hutting-contest-2/found_bug.md` | [0214][L14]：去重后修复映射 | 原文件未跟踪 |
| CONTEST 中的 5 份 Season-2 报告 | [0215][L15] | 日志未给出每份完整文件名，不补造路径 |
| contest-1/2/4 中的 3 份 `found_bug_s3.md` | [0216 S3][L16]：11 个独立问题 | 日志未完整列出目录路径，原文件未跟踪 |
| 桌面 `归档_副本.zip` 内 6 份 `found_bug_s4*.md` | [0223 S4][L23]：其中两份重复，5 份唯一报告 | 压缩包及原文没有随当前仓库交付；日志只有摘要简写 `a760b0f6…dc57` |

要取得原题全文，需要补回上述本地目录或压缩包。以下内容没有反向编造原题措辞，也没有把
简写 SHA 当作完整校验值。可以直接阅读链接中的历史日志，查看当时发现、修复及未运行项。

## 二、如何使用索引

- **宿主**：在开发机执行真实实现、库或脚本；一些测试用故障注入/系统调用替身，边界在各题说明。
- **客体**：需要匹配当前源码构建的 XOS、SDK 和 QEMU 等依赖。宿主通过不能代替客体通过。
- **源码检查**：现有测试只覆盖部分链路，需沿指定实现确认其余条件，不冒称有完整动态证据。

Python 入口均从仓库根执行，例如 `python3 tests/file_semantics.py`。客体入口运行前应完成
匹配构建；避免直接复用日志里旧 build id 的镜像。本文件是索引，本次编写没有重新执行下列全部
测试；实际本轮运行结果见 [综合审计说明](README.md)。历史 PASS 只代表对应日志当时的构建。

## 三、文件服务与 libc：Q01–Q10

### Q01：没有 O_CREAT 的打开操作会不会偷偷创建文件？

对不存在的文件分别执行 `O_WRONLY | O_TRUNC`、`O_WRONLY | O_APPEND`，随后查询目录；
应返回 ENOENT，文件仍不存在。再对已有文件执行 O_TRUNC，确认它确实被截为零。

源码：[files.cpp][files]。回归：[宿主 file_semantics.py][tfs] 与 [fixture][ffs] 第 1、2 组；
[客体 file_posix_guest.py][tposix] 与 [fixture][fposix]。历史：[0212][L12]。

### Q02：定位、截断与逻辑偏移是否互相干扰？

打开 10 字节文件，定位到 2，再截为 4 字节；当前偏移应仍为 2。定位到 EOF 之后时，
长度应不变；随后实际写入才扩大文件。检查逻辑偏移是否错误地直接依赖 FatFs 的物理游标。

源码：[files.cpp][files] 的 open description、seek、truncate。回归：[宿主][tfs] / [fixture][ffs]
第 3、5 组；[客体][tposix] / [fixture][fposix]。历史：[0212][L12]。

### Q03：扩大文件和越过 EOF 写入，会不会暴露旧簇内容？

将 `ABCD` 扩为 12 字节，新增字节应全零；在短文件 EOF 之后定位再写入，空洞也应全零。
注入扩展短写，要求返回 no_space，长度和原内容回滚。

源码：[files.cpp][files] 的零填充与回滚。回归：[宿主][tfs] / [fixture][ffs] 第 4、5、11、13 组；
正常零填充另有 [客体][tposix]。**真实近满 FAT 介质失败仍不是这些注入测试的覆盖。** 历史：[0212][L12]、[0215][L15]。

### Q04：I/O 部分完成后报错，会不会丢掉已完成进度？

使底层读写在完成若干字节后报错，检查服务是否返回实际字节数并推进偏移；
请求非零长度却因满盘写入零字节时，应报告 no_space，不能回成功零字节使 libc 误判为 EIO。

源码：[files.cpp][files]。回归：[宿主][tfs] / [fixture][ffs] 第 9、10、17 组，使用注入；
没有据此证明真实满盘客体行为。历史：[0212][L12]、[0216 S3][L16] 的 J。

### Q05：rename 替换在失败和重启后能否保住旧目标？

正常替换普通文件应得到新内容并清理 journal/backup。再注入 journal 短写、替换失败及恢复旧目标失败，
确认不会发布半份 journal；不能立即恢复时保留恢复材料，重启恢复后旧目标可找回，重复恢复幂等。

源码：[files.cpp][files]。回归：[宿主][tfs] / [fixture][ffs] 第 6、14、15 组，
[file_recovery_faults.py][trecovery]；[客体 file_recovery_guest.py][tgrecovery]，当前构建使用
`python3 tests/file_recovery_guest.py --system build`。历史：[0212][L12]、[0215][L15]、[0216 S3][L16]。

### Q06：把目录移动到自身后代，会不会破坏目录树？

建立父目录及其子目录，把父目录 rename 到该子目录内部；操作应被拒绝，父、子目录和已有内容保持可访问。
沿实现检查拒绝依据是否为目录项身份，而不仅是简单字符串前缀。

源码：[files.cpp][files]。回归：[宿主][tfs] / [fixture][ffs] 第 7 组；
[客体][tposix] / [fixture][fposix]。历史：[0212][L12]。

### Q07：路径规约是否跳过了必须存在的中间目录？

检查空路径、`missing/../x`、`plain-file/../x` 和普通文件尾斜杠。
其中不存在的中间项应 ENOENT，普通文件充当目录应 ENOTDIR；`unlink` 带普通文件尾斜杠时不得删除原文件。

源码：[newlib_syscalls.cpp][libc] 的 resolve_path_from 及各调用点。
回归：[客体][tposix] / [fixture][fposix] 的 empty/intermediate/trailing-slash 断言。
历史：[0212][L12]。这不是直接把 libc 路径逻辑复制到宿主模型的测试。

### Q08：描述符复用和 spawn 文件动作是否遵循实际执行顺序？

关闭 fd 0 后 open 应复用 0；关闭 0、1 后 pipe 应得到这两个最低空位。
登记相对 addopen 后改变 cwd，再 spawn，打开位置应依据 spawn 时的 cwd；
高号 addclose 后再 adddup2 同一 fd，应按动作顺序得到 EBADF。

源码：[newlib_syscalls.cpp][libc]。回归：[客体][tposix] / [fixture][fposix] 的 fd reuse、
relative addopen、ordered close/dup、pipe lowest fds。历史：[0212][L12]。

### Q09：句柄转移能否只靠调用者自报 PID 获得授权？

让目标 session 的认证 parent_pid 与调用者不一致，转移应拒绝；改为调用者的真实子进程关系才可通过。
沿内核到文件服务的链路核对 parent_pid 的来源，不能把请求中的目标 PID 本身当授权证明。

源码：[tasks.cpp][tasks] 的 sys_file_session、[process_abi.hpp][processabi]、[files.cpp][files]。
回归：[宿主][tfs] / [fixture][ffs] 第 8 组覆盖服务授权判断；宿主构造 session，
**没有独立证明完整内核认证链的客体对抗场景**。历史：[0212][L12]。

### Q10：255 字符 PATH 候选会不会被多算一个斜杠而拒绝？

PATH 项已以 `/` 结尾时，构造总长 255 字符的候选，创建文件并直接调用 posix_spawnp。
对于这个非 ELF 文件，应到达加载器并返回 ENOEXEC，而不是在路径阶段误报 ENOENT。
超过容量仍应拒绝，不能为修边界去掉长度限制。

源码：[newlib_syscalls.cpp][libc] 的 posix_spawnp / resolve_path_from。
回归：[客体][tposix] / [fixture][fposix] 的 trailing-slash PATH boundary，直接覆盖 255 字符案例。
历史：[0213][L13]；该日志说明当时树内无普通应用调用者，不应把探针当成熟应用流程。

## 四、整数、容器和宿主工具：Q11–Q18

### Q11：JSON 是否接受 INT64_MIN，同时拒绝两端溢出？

输入 `-9223372036854775808`、`9223372036854775807` 应成功；两端再越界 1 应失败。
检查负数逐位累积上限是否允许 `INT64_MAX + 1`，同时避免计算过程自身溢出。

源码：[xypm_native.hpp][xypmnative]。回归：[宿主 xypm_json_cases.py][tjson] 与
[json_cases.cpp][fjson]。历史：[0213][L13]。不需要启动客体才能运行该解析器回归。

### Q12：diskio 扇区加法会不会在 32 位处绕回？

在 32 位 LBA 边界附近组合 sector/count，检查范围校验和循环访问的绝对扇区；
报告设备容量超过 LBA_t 上限时应按既有契约截断，不能静默回绕到小容量。

源码：[fatfs_diskio.cpp][diskio]。回归：[宿主 fatfs_diskio_cases.py][tdiskio] 与
[diskio_cases.cpp][fdiskio]，使用 block syscall 桩验证局部算术。
历史：[0213][L13]。**没有在超过 2^32 扇区的真实设备上验证。**

### Q13：bundle 格式错误是否在写盘前被拒绝？

分别破坏成员间/尾部零填充、保留字段、成员类型或 ELF/ustar 魔数；构建器和解析器都应拒绝。
CLI 自检失败时不应先留下输出容器。检查客体安装器是否实施与宿主相符的格式约束。

源码：[xos_bundle.py][bundle]、[file_ui.cpp][fileui]。回归：[宿主 test_xos_bundle.py][tbundle]
的 BundlePaddingAndNames / BundleCli / BundleReject；[客体 bundle_installer_reject.py][tbundlereject]
覆盖 bad-name、reserved1、bad-magic、non-elf-legacy 等具体向量，不能认为每个宿主负例都已有独立客体向量。
历史：[0214][L14]。

### Q14：成员名称、大小写和名称区布局能否绕过校验？

尝试目录穿越、反斜杠、DOS 保留名、尾点/空格、大小写碰撞及 type5 名称与 dash 目标冲突；
再把 name_off 改为重叠或在名称区留空。应在提交任何成员前拒绝；合法容器仍应可安装。

源码：[xos_bundle.py][bundle]、[file_ui.cpp][fileui]。
回归：[宿主][tbundle] 的名称/compact/unused-tail 测试；[客体拒绝][tbundlereject] 的 name-overlap，
合法对照 [iso_bundle_install.py][tbundleinstall]。历史：[0214][L14]、[0215][L15]、[0216 S3][L16] 的 C。

### Q15：同大小旧文件和后序坏摘要，会不会绕过安装校验？

在目标盘预放同大小但不同内容的文件，确认安装器哈希的是磁盘上的目标，而不是仅重算随包载荷。
再损坏后序成员摘要，确认全员预检失败时没有先写入前序成员。

源码：[file_ui.cpp][fileui]。回归：[客体 bundle_preexisting_digest.py][tpreexisting] 与
[bundle_installer_reject.py][tbundlereject] 的 later-digest。
历史：[0214][L14]、[0215][L15]。这只保证预检，不等于运行时故障下具有整包事务回滚。

### Q16：安装 marker 是否绑定具体 bundle，并支持失败后重试？

同一工作盘先安装 bundle A，再换为 B，marker 必须随启动载荷摘要变化，不能因旧 marker 跳过 B。
沿 supervisor 检查 bundle 未完整安装、包安装失败、marker 写失败时是否仍错误宣布成功；
检查 ensure 的未装/同摘要/异摘要分支是否支持重试。

源码：[file_ui.cpp][fileui]、[supervisor.cpp][supervisor]、[xypm.cpp][xypm]。
回归：[客体 bundle_marker_identity.py][tmarker] **使用 fake xypm**，实际验证 marker 身份路径；
[iso_bundle_reboot.py][treboot] 提供重启入口。历史：[0215][L15]。
真实 xypm ensure 的客体故障注入在日志中明确未完成，不能用 fake xypm 的通过替代。

### Q17：宿主 helper 缓存会不会信任被替换或无法解码的文件？

检查源码摘要未变但二进制变更、符号链接、非预期属主/权限、非 UTF-8 stamp 等情况；
无效缓存应拒绝复用并走重建，不能执行未经核对的旧 helper，也不能直接因解码异常退出。

源码：[xypm_image.py][xypmimage]、[work_disk.py][workdisk]。
回归：[宿主 xypm_host_cache.py][txcache]、[work_disk_cache.py][twcache]。
后者的部分重建流程使用编译替身；属主差异也有模拟。历史：[0214][L14]、[0215][L15]、[0216 S3][L16] 的 G。
这些结果不等于真实多用户共享临时目录攻击复现。

### Q18：ISO 名称和 work_disk 路径边界是否提前、清晰地拒绝？

ISO 根目录的重名、仅大小写不同名、带目录分隔符、超长名应在输出前干净拒绝，不抛 traceback；
work_disk transfer 的反斜杠路径应在执行 helper 前拒绝，不能绕过保留名/分量规则。

源码：[make_iso.py][makeiso]、[work_disk.py][workdisk]。
回归：[宿主 make_iso_names.py][tisoname] 与 [work_disk_cache.py][twcache]。
历史：[0215][L15]、[0216 S3][L16] 的 B/D。
**当前审计分支的 ISO 边界为 219 字符接受、220 字符拒绝**；这是本轮补齐目录记录填充后的边界，
历史 S3 的 220/221 不是当前期望。work_disk 的拒绝顺序测试有 helper 桩，不冒称实际执行了恶意路径。

## 五、S3 中容易漏掉的文件回归：Q19–Q20

### Q19：只改文件名大小写，是否真的修改了磁盘目录项？

将 `Case.txt` 改为 `case.txt`，随后枚举父目录，确认存储的名称发生变化。
不能仅调用 f_stat 并查看返回名称：该 API 可能回填请求中的拼写，使错误测试也通过。

源码：[files.cpp][files] 的 names_equal_exact / rename。
回归：[宿主][tfs] / [fixture][ffs] 第 12 组，用真实 f_opendir/f_readdir 检查。
历史：[0215][L15]、[0216 S3][L16] 的 A 及其“假阴性”测试修正。

### Q20：零长度写和空洞填充后的失败，会不会留下错误文件长度？

定位到 EOF 之后写零字节，长度和逻辑偏移都应保持不变。
再让空洞填充先成功、实际数据写入返回零字节，要求报告 no_space 并恢复原长度；
失败后重试仍必须使用原先请求的逻辑偏移。

源码：[files.cpp][files] 的 write / undo_failed_write。
回归：[宿主][tfs] / [fixture][ffs] 第 16、17 组；本轮又补充了逻辑偏移保留断言。
历史：[0216 S3][L16] 的 E/F/J。历史记录明确 seek-失败没有独立注入向量，不能把共用回滚代码等同于分支全覆盖。

## 六、S4 窗口、输入和音频：Q21–Q24

### Q21：窗口配额与焦点销毁是否遵守真实窗口身份？

多个 session 分别创建窗口，验证每 session 8 窗的模型配额没有被全局 8 槽误限。
销毁、隐藏或断开焦点窗口后，键盘应交给剩余可见窗口；无效窗口 ID 0 不能匹配空槽。

源码：[window_manager.cpp][wm]、[service.cpp][interactium]。
回归：[宿主 interactium_model_test.cpp][timodel] 的容量及焦点生命周期场景；
[interactium_guest.py][tiguest] 是客体启动/双窗口显示入口，**未证明每项输入和配额边界均已在客体验收**。
历史：[0223 S4][L23] 的 W1/W4。guest surface_capacity=8 是单独的像素池预算，不能与模型窗口表混为一谈。

### Q22：输入溢出、跨窗移动和松键，会不会让客户端状态卡住？

填满输入队列再输入，检查 lost/resync 以及严格递增序列号；指针移到另一窗口时旧窗口应收到离开信息；
在 A 按下、切焦点到 B 后松开，release 应回到 A，A 销毁后则不应误投 B。

源码：[service.cpp][interactium]。
回归：[宿主模型][timodel] 与 [transport][titransport]；[客体 Interactium 入口][tiguest]
不替代完整 PS/2→服务→QPA held-state 验证。
历史：[0223 S4][L23] 的 W2/W3/W5。本轮追加的重复按键归属及 display 级 resync 场景属于后续回归，
不冒充 S4 原题已有内容。

### Q23：音频请求是否能完成握手，并让对端读到关闭前的回复？

检查 SDK 发出的 version/size/reserved，命名 IPC 端点是否走正确的 readiness 等待接口；
服务端应把 ipc_send 返回 0 识别为成功。close/busy 回复应在有界等待对端读取后关闭，
满队列要按既有重试规则处理，断线与截止时间应明确传回。

源码：[audio_client.hpp][aclient]、[audio_service.cpp][aservice]。
回归：[宿主 audio_client_host_test.cpp][taclient]、[audio_service_reply_test.cpp][taservice]。
这两个入口含 syscall/邮箱替身；客户端测试还包含部分服务端条件的副本，不能声称整个真实服务链已经联调。
历史：[0223 S4][L23] 的 A1/C1/C2。**音频客体端到端在该记录中未运行**；对端始终不读时的 40 ms 关闭是已披露的有界行为。

### Q24：非法音调参数会不会变成“成功的休止符”，最长音符会不会撞租约？

输入 `abc`、溢出数字、`440x` 或空频率应参数错误退出；字面值 `0` 应保留休止符语义。
对协议允许的 2,000 ms 音符，检查 speaker 租约是否含启动/调度余量，避免到唤醒时已被先行撤销。

源码：[audio_tone.cpp][atone]、[audio_abi.hpp][audioabi]、[tasks.cpp][tasks]。
回归：[宿主 audio_tone_args_test.cpp][tatone]（clock/sleep/play 替身）、
[pc_speaker_lease_check.py][tlease]（真实常量编译与小型时序模型）。历史：[0223 S4][L23] 的 A2/K1。
模型不代替真实硬件或客体；额外调度延迟达到 500 ms 的边界仍需按契约评估。

## 七、一道必须辨伪的历史报告：不计入上述 24 题

S4 的 T1 声称“Interactium close 只关 send，因此 receive 泄漏”，[0223][L23] 已明确反驳。
检查 [ipc_transport.cpp][transport] → [sdk.hpp][sdk] 的 ipc_channel_close →
[tasks.cpp][tasks] 的 revoke_ipc_channel：配对端点共享 channel_id，关闭会撤销整对。
不要与关闭单个 generic_channel 端点的 channel_close 混淆，也不要据此再添加冗余修复。

原日志引用的临时逻辑抽取模型没有作为独立测试入口随当前仓库提交；这里提供源码链和历史结论，
不伪造一个可运行的原始测试文件。

## 八、可直接选择的现有运行入口

以下是入口清单，不是新的统一测试框架。按所选题目运行相应命令，查看测试本身声明的依赖与范围。

| 执行位置 | 命令 / 文件 | 关联题目 |
|---|---|---|
| 宿主 | `python3 tests/file_semantics.py` | Q01–Q06、Q09、Q19–Q20 |
| 宿主 | `python3 tests/file_recovery_faults.py` | Q05 |
| 宿主 | `python3 tests/xypm_json_cases.py`、`python3 tests/fatfs_diskio_cases.py` | Q11–Q12 |
| 宿主 | `python3 tests/test_xos_bundle.py` | Q13–Q14 |
| 宿主 | `python3 tests/xypm_host_cache.py`、`python3 tests/work_disk_cache.py`、`python3 tests/make_iso_names.py` | Q17–Q18 |
| 宿主 | `python3 tests/pc_speaker_lease_check.py` | Q24 |
| 客体 | `python3 tests/file_posix_guest.py` | Q01–Q03、Q05–Q08、Q10 |
| 客体 | `python3 tests/file_recovery_guest.py --system build` | Q05 |
| 客体 | `python3 tests/bundle_installer_reject.py`、`python3 tests/bundle_preexisting_digest.py` | Q13–Q15 |
| 客体 | `python3 tests/bundle_marker_identity.py`、`python3 tests/iso_bundle_reboot.py` | Q16，注意 fake xypm 限制 |
| 客体 | `python3 tests/interactium_guest.py` | Q21–Q22 的启动/显示补充 |

Q21–Q24 的 C++ 宿主文件直接测试实现或已说明的边界替身，链接已列在题目内；不要将它们改为复制
业务逻辑的新测试。安装镜像和包相关客体入口还需要相应 bundle/seed/SDK 资产，缺失资产时应记录未运行。

[L12]: ../../work_log/0212_file_service_found_bug_fixes.md
[L13]: ../../work_log/0213_second_bug_hunt_fixes.md
[L14]: ../../work_log/0214_bundle_installer_hardening.md
[L15]: ../../work_log/0215_s2_bug_hunt_fixes.md
[L16]: ../../work_log/0216_s3_contest_report_fixes.md
[L23]: ../../work_log/0223_s4_contest_report_fixes.md
[files]: ../../../src/user/services/files.cpp
[libc]: ../../../src/user/libc/newlib_syscalls.cpp
[tasks]: ../../../src/kernel/arch/x86_64/tasks.cpp
[processabi]: ../../../src/shared/include/xos/process_abi.hpp
[xypmnative]: ../../../src/user/programs/xypm_native.hpp
[diskio]: ../../../src/user/services/fatfs_diskio.cpp
[bundle]: ../../../scripts/xos_bundle.py
[fileui]: ../../../src/user/services/file_ui.cpp
[supervisor]: ../../../src/user/programs/supervisor.cpp
[xypm]: ../../../src/user/programs/xypm.cpp
[xypmimage]: ../../../scripts/xypm_image.py
[workdisk]: ../../../scripts/work_disk.py
[makeiso]: ../../../scripts/make_iso.py
[wm]: ../../../src/user/interactium/window_manager.cpp
[interactium]: ../../../src/user/interactium/service.cpp
[transport]: ../../../src/user/interactium/ipc_transport.cpp
[sdk]: ../../../src/user/include/xos/sdk.hpp
[aclient]: ../../../src/user/include/xos/audio_client.hpp
[aservice]: ../../../src/user/programs/audio_service.cpp
[atone]: ../../../src/user/programs/audio_tone.cpp
[audioabi]: ../../../src/shared/include/xos/audio_abi.hpp
[tfs]: ../../../tests/file_semantics.py
[ffs]: ../../../tests/fixtures/file_semantics/file_semantics.cpp
[tposix]: ../../../tests/file_posix_guest.py
[fposix]: ../../../tests/fixtures/file_posix/file_posix.c
[trecovery]: ../../../tests/file_recovery_faults.py
[tgrecovery]: ../../../tests/file_recovery_guest.py
[tjson]: ../../../tests/xypm_json_cases.py
[fjson]: ../../../tests/fixtures/xypm_json/json_cases.cpp
[tdiskio]: ../../../tests/fatfs_diskio_cases.py
[fdiskio]: ../../../tests/fixtures/fatfs_diskio/diskio_cases.cpp
[tbundle]: ../../../tests/test_xos_bundle.py
[tbundlereject]: ../../../tests/bundle_installer_reject.py
[tbundleinstall]: ../../../tests/iso_bundle_install.py
[tpreexisting]: ../../../tests/bundle_preexisting_digest.py
[tmarker]: ../../../tests/bundle_marker_identity.py
[treboot]: ../../../tests/iso_bundle_reboot.py
[txcache]: ../../../tests/xypm_host_cache.py
[twcache]: ../../../tests/work_disk_cache.py
[tisoname]: ../../../tests/make_iso_names.py
[timodel]: ../../../tests/interactium_model_test.cpp
[titransport]: ../../../tests/interactium_transport_test.cpp
[tiguest]: ../../../tests/interactium_guest.py
[taclient]: ../../../tests/audio_client_host_test.cpp
[taservice]: ../../../tests/audio_service_reply_test.cpp
[tatone]: ../../../tests/audio_tone_args_test.cpp
[tlease]: ../../../tests/pc_speaker_lease_check.py
