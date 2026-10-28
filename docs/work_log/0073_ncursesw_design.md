# 0073：宽字符终端库设计

2026-10-28。用户提出以可复用的系统接口为目标，要求将 ncursesw 底座设计写入项目并
提交。新增[设计](../plans/ncursesw.md)：用户态终端、libc 宽字符/locale、SDK、
terminfo、ncursesw 和应用分层；明确 W0–W3、真实接口与提交后的客体验收边界。
第二档由 kg 初选调整为先评估 ncursesw，再优先评估 nano；kg 留作备选。未改变宪法、
分配 ABI 或移植软件。

另根据当前 `files.cpp`、FatFs 配置和[0068](0068_utf8_filenames.md)修正多语言计划中
过期的 ASCII 路径状态：UTF-8 文件名已有受限实现与证据，完整大小写/归一化和包路径等
仍有边界；未改写旧报告。修改 `docs/plans/ncursesw.md`、`terminal_editor.md`、
`multilingual.md`、`docs/state.md` 及本记录。

本组仅文档，未构建系统、SDK、ncurses、nano，也未运行客体验收；按用户要求先提交所有
相关改动再验收。历史资格不改绑。下一步先冻结 ncurses 版本及目标依赖探针，分别制定
终端、locale 与库 profile，保留独立文件范围和 ABI 登记纪律。
