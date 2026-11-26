# b8dc9a24 · ClarkE 的 WebCore 字形依赖

以 #267 的 `1b4ea7d0` 为基底，独立构建 WebCore 共用的字形库。锁定的 QtBase
6.8.3 提供 FreeType 2.13.3 和 HarfBuzz 10.4.0，字形库与签名 glibc
SDK 及 ICU4C 79.1 使用同一目标配置。Linux ARM64 宿主的 GCC 16.2.0、
Binutils 2.47 生成 `libfreetype.a`、`libharfbuzz.a` 和 `libharfbuzz-icu.a`。
产物前缀包含公开头、原始许可文本及每个文件的摘要。
[复现入口](../../src/ports/webkit/fonts/README.md)

从锁定的 WPE WebKit 2.54.2 归档读取 CMake 模块。WPE 的 HarfBuzz ≥2.7.4
且包含 ICU 组件，以及 FreeType ≥2.9.0 两项配置检查，均解析到本次构建的
三份 XOS 静态归档。CMake 4.4.4 只在目标前缀中查找库和头文件。
此版本的 `OptionsWPE.cmake` 默认启用 Skia，并显式关闭 Cairo。这一证据更新
原计划中的渲染路径假设。完整 WPE 配置和自定义端的实际页面输出各有后续门。

首轮诊断对 probe 使用 `--gc-sections`，生成的 ELF 丢失了 `_init` 和 `_fini`
的 CRT 续段，QEMU 记录了启动故障。完整链接后，两个入口均恢复正常返回指令。
阶段性重链回执记录了 xsh 实测。正式构建从锁定的原始输入重编，并独立重建本次
验收镜像。

`b8dc9a24` 的 QEMU 11.1.2 镜像 `e4d7002a8d6b5368` 验证了 xsh 的两条
路径。缺失字体以状态 2 退出。实际 DejaVu Sans 的 `fi` 由 HarfBuzz 解析为
字形 5042，FreeType 产出 13×18 灰度栅格和 124 个非零像素。退出后保留
129696 空闲页、3 项任务、1 条完成记录。dash 已启动，同次的 120 秒检查时限
到达时尚未取得子程序的结果。单独保留该次回执。
[静态目标构建回执](../reports/clarke_webcore_font_stack_20261126/target_inputs.json) ·
[首轮链接故障](../reports/clarke_webcore_font_stack_20261126/initial_crt_failure.json) ·
[120 秒客体回执](../reports/clarke_webcore_font_stack_20261126/guest_120_second_limit.json)

按 `fbb84a4a` 重建的普通镜像 `f1d9b15ae90f6fba`，用同一已核对的静态 ELF
在 QEMU 11.1.2 复验。xsh 和 dash 均实测缺失字体退出 2，正常字体退出 0，
得到相同的字形编号、尺寸和非零像素计数。四次运行后资源均为 129696 空闲页、
3 项任务、1 条完成记录。正常样例从命令到返回分别耗时 13.506 秒和 184.792 秒，
所以大静态 ELF 的 dash 用例保留单独可配的验收时限。
[正式双入口回执和摘要](../reports/clarke_webcore_font_stack_final_20261126/manifest.json)
