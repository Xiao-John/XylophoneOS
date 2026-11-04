# 0187 W1/ncurses 最终验收（组合源码重建 + 全量客体门槛）

2026-11-03。接手并完成 W1 终端线的最终验收；全部基于当前提交 `ac43923`
（本分支 = 远端 main 全量 + 本线 173 提交）的组合源码、匹配 UTF-8 SDK 候选、
独立系统镜像与专用测试盘，在实际 QEMU 串口上执行。未推送、未开 PR。

## 构建链（build/w1_final_acceptance/，全部隔离子目录）

1. `build_utf8_newlib.py`（冻结 newlib 归档，`--jobs 8`）→ single/prefix；
2. `build_utf8_sdk_candidate.py` → UTF-8 SDK 候选（MB_CAPABLE）；
3. `probe_ncursesw.py --build --no-sigwinch --xopen-source 700` →
   `libncursesw.a` 构建成功（archive_valid=true；缺 `--build` 只做 configure、
   缺 `_XOPEN_SOURCE=700` 则 `wcwidth` 隐式声明编译失败——两处均为本次实测踩准）；
4. `build_ncursesw_terminfo.py` → xterm terminfo 候选（MIXEDCASE/XNAMES 布局核验过）；
5. `prepare_ncursesw_sdk.py` → composed 候选（tree_sha256 绑定 probe+terminfo）；
6. `probe_ncursesw_consumers.py`（对 UTF-8 候选交叉链接 5 个夹具）+
   `ncurses_sdk_candidate_smoke.py`（对 composed 独立链接——其产物才是
   guest/freeze 组合模式的 `--consumers`，含 candidate_tree_sha256）；
7. 四个系统镜像：normal / ncurses-supervisor / terminal-supervisor / clock-irq。

## 验收门（全部 PASS）

| 门 | 结果 |
|---|---|
| `unicode_width_consistency`（对冻结 newlib 宽度表） | PASS |
| `ncurses_sdk_candidate_smoke`（composed 独立链接） | PASS ×2 |
| `terminal_handoff_probe`（terminal-supervisor 系统，15 组客体检查） | PASS |
| `clock_irq_guest`（clock-irq 系统，主线时钟/IRQ 回归） | PASS |
| `ncurses_guest_probe`（ncurses-supervisor 系统，非 xsh 模式） | PASS |
| `ncurses_screen_guest`（normal 系统，`--xsh --composed`，GNU Screen 24x80 实机附着，CJK/组合字符字节断言） | PASS |
| **`freeze_ncursesw_subset`（封顶：12 项 `xsh_*` 子集门 + Screen/系统/候选/消费者四方哈希一致性）** | **PASS** → `build/w1_final_acceptance/frozen/`（delivery + evidence + receipt；guest_report=passed_probe/12 checks，screen=passed_subset） |
| `docs_consistency` / `abi_doc_consistency` | PASS |

## 边界（如实）

- 验收范围 = freeze 的 12 项 xsh 子集 + 上列各门；不等于完整 W1/W2（契约原文
  边界不变：忙 FIFO、设备时序、动态尺寸/信号、完整作业控制等仍标注未运行）。
- 本次未改任何仓库文件（工作树干净）；构建产物均在 build/ 隔离子目录。
- 未推送、未开 PR（按指令待命）。
