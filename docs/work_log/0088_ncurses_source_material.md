# 0088：ncurses 源码锁与许可材料

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-29。以 0087 已校验的 6.5 原包为候选，在 `src/ports/ncurses` 保存来源锁、
上游原始 `COPYING` 和当前范围说明；组件清单登记源码包与许可材料摘要。原包、
锁定文件、构建参数和补丁将来须一同作为对应源码材料；当前没有目标库或发行。
上游 COPYING 的保存不等于逐成员条款、静态分发义务或所有衍生文件均已审计。

`scripts/probe_ncursesw.py` 改为读取锁文件，检查存档与许可文本、记录整个目标 SDK
树哈希，并在配置/构建结束后确认 SDK 和锁未变化。执行：

```text
python3 scripts/probe_ncursesw.py --archive .cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz --sdk ${XOS_SCRATCH}/xos_w1_utf8_strict_sdk_20261029/sdk --output ${XOS_SCRATCH}/xos_ncurses_locked_probe_20261029 --build
```

源和 SDK 完整性检查通过，configure 退出 0；目标库构建退出 2，仍因为缺少 `sgtty.h`。
SDK 树 SHA256 `db96154268cc796ef180ec621019f3cd1c89ba0b43bb041ec1b00a7e82c69b27`，
源码锁 SHA256 `6ce494e41d9a032782b83794c3336725dd41d8b7a9a1263a34e10d5a61d488ee`。
这只是诊断结果；W0 未冻结，W1 终端对象与等待和 W2 目标库/terminfo 仍未实现。

串行执行 `python3 scripts/build.py --output-dir build/w1_ncurses_source_lock_20261029`，
build ID `1182a4bcd008ab24`；`python3 scripts/license_audit.py --build
build/w1_ncurses_source_lock_20261029` 材料检查 7 项通过。它不证明逐成员许可审计、
静态分发或本次修改的 guest 行为。相关修改提交后才进行客体验收。
