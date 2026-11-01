# 0082：单线程多字节 SDK 候选

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-29。W1 在 `codex/ncursesw_w1` 上接续，分支快进到更新后的 main `39083f9`。
本次完成可重建的隔离 SDK 候选，不改变既有 SDK 或已经冻结的证据；W1 未完成。

新增 `scripts/build_utf8_sdk_candidate.py`。它核对 single 多字节 newlib 候选的回执和
各产物，在新目录安装配套头与运行库，按现有 SDK 顺序覆盖 XOS 的头，重新编译 libc
适配、loader 与 CRT，并保存命令、输入和工具哈希。manifest 和构建回执明确标为
`built_unverified`，不是注册的应用 profile，也不是正式发行 SDK。没有替换系统运行库。

旧 `/tmp` 候选已不存在，本次重新执行：

```text
python3 scripts/build_utf8_newlib.py --archive .cache/xos_seed/threading_sources/newlib-4.6.0.20260123.tar.gz --output ${XOS_SCRATCH}/xos_w1_newlib_20261029 --jobs 8
python3 scripts/build_utf8_sdk_candidate.py --newlib-prefix ${XOS_SCRATCH}/xos_w1_newlib_20261029/single/prefix --output ${XOS_SCRATCH}/xos_w1_utf8_sdk_20261029
```

单线程候选 SDK 构建成功，树 SHA256 为
`daa0271f9cd6d77ca7dcc7571d79a4b5dc223264efb3183d1e057ee715e8e958`。使用该候选的
CRT、头和静态库交叉链接 `tests/fixtures/ncursesw/wide_locale_probe.c` 成功，ELF SHA256
`2c0df67ae37733a6cc9516e9a40aa7d72534a1fcf0e6193c37fb7b24ee993a02`。这只是链接检查；
guest、UTF-8 行为、线程兼容与完整 SDK 资格均未验收。临时目录可重建，不作为唯一源码。

线程候选的 newlib 构建完成。为避免覆盖共享日志，线程 SDK 构建器增加可选 `--logs-dir`；
执行 `python3 scripts/build_threading_sdk.py --newlib-prefix ${XOS_SCRATCH}/xos_w1_newlib_20261029/threaded/prefix --output build/w1_utf8_threaded_20261029 --logs-dir build/w1_utf8_threaded_logs_20261029` 成功。
其 manifest SHA256 为 `b946d06aeea4ca2318e44b4f3831281083b58bfeb2b911c047484f245b02ce72`。
直接用该非 C++ SDK 的 `libxos.a` 全归档链接同一探针失败：线程对象要求
`__gxx_personality_v0`。需要构建匹配的线程 C++/unwind 运行库并重新链接；不能用其他
SDK 的库混入后宣称 profile 已验证。线程运行、并发 locale 和退出回收均未运行。

终端对象、权限、模式、IRQ 及真实等待仍未实现，W0 的 ncurses 目标调用路径仍须冻结。
按用户要求，相关改动提交后才做客体验收；完成全部 W1 及验收后才整合 main、提交 PR。
