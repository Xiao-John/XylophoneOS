# 4cc23087 · ClarkE 的原生 WebCore HTML 分词

从 WPE 2.54.2 的锁定归档编译真正的 `HTMLTokenizer`、分段输入、实体解析和实体
搜索。实体表和名称由同一归档的上游生成器生成。目标编译复用 glibc C/C++ SDK、
ICU4C 79.1、JSC 生成配置及已锁定的 WTF 和 bmalloc 静态归档。
[构建入口](../../src/ports/webkit/tokenizer/README.md) ·
[静态目标回执](../reports/clarke_webcore_html_tokenizer_20261126/target.json)

探针从源文件派生独立默认 options 构造函数，对不使用的 DOM 配置路径只做目标对象
可达性裁剪。裁剪发生在目标对象的可重定位链接阶段。最终 ELF 保留标准 glibc CRT
入口并通过目标 ELF 检查。编译和链接仍显示部分 glibc/平台调用的现有告警，其中
`raise`、`sleep`、`sysconf`、`madvise`、`__getcwd` 的其他调用路径另行验收。

合入 #278 和 #279 后从 `4cc23087` 重建普通镜像 `0b8800877d41f80e`。
QEMU 11.1.2 在 xsh 打开真实 FAT HTML 页，得到 DOCTYPE、规范化的标签和属性名、
解码的属性值、跨分段的 `&nbsp;` 和 EOF。正常输入以 0 退出，缺失文件以 2 退出。
目标 ELF 和页文件都在启动前从 FAT 读回并比对，两种路径都恢复 129696 空闲页、3 个
任务和 1 条完成记录。LibXml2 的合法与失配闭合场景用同一新镜像复验通过。
[客体与组合复验回执](../reports/clarke_webcore_html_tokenizer_20261126/manifest.json)

本次交付覆盖原生分词和 XML 前置。DOM/tree builder、CSS、布局、Skia 和 Qt
视口仍沿本地页计划逐段验收。
