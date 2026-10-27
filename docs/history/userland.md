# 用户态与CPython：实现摘要

截至2026-10-27。源码和构建接口见src/ports/cpython/README.md；范围见[移植计划](../plans/cpython.md)。

## CPython已实现

| 阶段 | 行为与证据 |
|---|---|
| PY0 | 静态CPython 3.14.9启动/脚本；初版ad85d8438b4101d66483，SDK build2c3876e640840ff5；无害exec_prefix提示不等于缺模块全通过 |
| PY1 | stage布局、argv/cwd/env、同目录import、二进制文件、6/6真实操作/异常与回收；build/cpython_py1_report.json |
| T3-PY | 真实pthread/GIL/等待、线程与C++运行库接入，各自冻结SDK，不用空锁模拟 |
| PY2 | basic REPL、input/EOF/退格与JSON存档/sync重启；无readline/history或SIGINT保证 |
| PY3 A1 | hash/HMAC、pathlib、argparse、dataclasses、tomllib、Decimal、XML、未压缩ZIP真实操作 |
| PY3 A2/A3 | zlib1.3.2静态扩展、gzip/ZIP/zipimport与损坏输入；受限离线包/固定依赖安装；不等于在线pip |
| PY3 B1 | sys63 getentropy，最多256字节，CPUID RDRAND+有界重试；缺硬件ENOSYS、硬件失败EIO，无伪随机回退 |
| PY3 B2 | sys64 RTC UTC启动样本+PIT增量、gettimeofday/CLOCK_REALTIME、POSIX TZ和ZoneInfo/tzdata2026.5 |
| PY3 B3 | SQLite3.54.1静态XOS VFS：事务/约束/busy/损坏、sync重启重开与完整性 |
| PY3 B4 | bzip2 1.0.8、liblzma5.8.4、zstd1.5.7：静态流式roundtrip、损坏/截断、257字节输出限额 |

A1/A2原样本系统4c79f3a789dcff61；zlib指纹cbc19df997a4ab9d6acf、Python2b6c1342ebe6fb8c22dc。
B1系统46cb97b1555633f1验有/无RDRAND；信任CPU/hypervisor，不提供RDSEED/virtio-rng。
B2–B4最终系统6251d26b611a388d，xos.img SHA256
cc5524eb0b57a528f5db973e888b18356ecb5caf16ed767a604a221064d844d0；
Python指纹11c39c52e451a9499450，1199文件stage摘要
74f45b5baa1be78a5d252d608bd2dcbb526da3b91113c4e61a8e1abba104e4a6。
SDK manifest 22960edc51be4a8a8bc0726c2179c2200b02509d49bc2aceb3640aa463d60c13。

B2报告build/cpython_py3_b2_report.json；B3/B4分别在.cache/xos_seed/cpython/sqlite与
compression下的guest_report_11c39c52e451a9499450及guest_report_b4_11c39c52e451a9499450。
三项passed，B2资源[130336,2,0]稳定。旧A段缺熵/墙钟说明不覆盖B段当前能力。

边界：无VM挂起独立RTC刷新、SQLite WAL/跨进程锁/每库多个可写连接、socket/TLS、动态扩展
或完整POSIX资格；B3是单进程rollback journal。材料检查不代替第三方逐成员许可审计。

## 其他用户态

Open Adventure1.12固定源码，XOS内由最小yaml子集生成数据并用GCC/G++构建；生成结果与
PyYAML6.0.3参考逐字节一致。readline为SDK适配，固定种子/时间和去SIGINT属于游戏端口
开发边界；完整中文游戏流程仍未验。移植菜单只作候选，不能沿用其旧“无线程/无fork”判断。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0028_userland_port_catalog"></a>
- `docs/history/userland.md#log-0028_userland_port_catalog`
<a id="log-0029_cpython_port_plan"></a>
- `docs/history/userland.md#log-0029_cpython_port_plan`
<a id="log-0030_cpython_py0"></a>
- `docs/history/userland.md#log-0030_cpython_py0`
<a id="log-0034_adventure"></a>
- `docs/history/userland.md#log-0034_adventure`
<a id="log-0038_cpython_py1"></a>
- `docs/history/userland.md#log-0038_cpython_py1`
<a id="log-0043_cpython_t3_py"></a>
- `docs/history/userland.md#log-0043_cpython_t3_py`
<a id="log-0046_cpython_py2"></a>
- `docs/history/userland.md#log-0046_cpython_py2`
<a id="log-0049_cpython_py3_a1_a3"></a>
- `docs/history/userland.md#log-0049_cpython_py3_a1_a3`
<a id="log-0052_cpython_b1_entropy"></a>
- `docs/history/userland.md#log-0052_cpython_b1_entropy`
<a id="log-0058_cpython_py3_b_segment"></a>
- `docs/history/userland.md#log-0058_cpython_py3_b_segment`
