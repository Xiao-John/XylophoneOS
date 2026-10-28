# 0076：多字节 libc 目标链接探针

2026-10-28。继续 W1 前期缺口，不改变系统 SDK 或既有资格；没有做客体验收。

- 新增 `scripts/probe_utf8_link.py`：校验 single 候选全部产物与构建回执，在独立目录以
  候选头重新编译 XOS libc 适配层，再与候选 libc/libm 和现有 SDK 的 CRT、链接脚本及
  loader archive 链接独立探针。输出回执记录工具、命令、输入和 SDK 树哈希，明确标注
  `cross_linked_guest_not_run`；它不是可分发 SDK，也不证明其运行时 ABI 或行为。
- `wide_locale_probe.c` 增加分片中文、非法 UTF-8 的 EILSEQ、ASCII/CJK/组合字符宽度
  断言。它们只是待运行测试，尚无客体结果。
- newlib 的 `_MB_CAPABLE` 会改变 `struct _reent` 内容和 `_MB_LEN_MAX`，线程控制块也
  包含该结构；因此不能只把候选 libc 替换到用旧头构建的 SDK 中。先前一次直接混链
  虽能链接，但不能证明兼容，不用于资格。第一次重编因上游 `dirent.h` 覆盖 XOS 的
  头而失败；按现有 SDK 生成顺序将 XOS 头置于上游之前后成功。
- 命令：`python3 scripts/probe_utf8_link.py --newlib-prefix /tmp/xos_newlib_utf8_receipted_20261028/single/prefix --sdk build/input_edit_final/sdk --output /tmp/xos_w1_locale_link_final_20261028`。
  编译/链接退出 0，ELF SHA256 `cdecab0204d6c43f63fea21e218915735459b048053511dcc319d3cf39aa733d`；
  输入旧 SDK 树 SHA256 `b33f5203b794e07417d554605b5749bcc45099702500fffb4371c21403df8c76`。
  临时回执位于上述输出目录，临时文件可重建。该 SDK 属于旧组合，不是当前系统验收。

下一步：以当前源码生成绑定候选运行库的正式隔离 SDK，分别重编 single/threaded 全部
适配和 CRT 并核实 ABI、内存及锁；按 W0 冻结 ncurses 实际调用路径；实现受控终端、
等待、生命周期和权限。相关修改全部提交后才做客体验收，尚不能宣布 W1 完成。
