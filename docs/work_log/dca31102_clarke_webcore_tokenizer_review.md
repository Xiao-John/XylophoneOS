# dca31102 · WebCore 分词探针源码快照

对 #283 的 `a4c9bcdb` 修订构建输入。探针在构建目录保存一次源码快照，交叉编译和
回执复用该字节序列。源码取样完成后，在独立工作树暂时加上令编译出错的指令，直到
目标编译退出仍保留该内容。实际目标构建通过，回执记录快照摘要，产出的 ELF 与前次
字节一致。随后恢复工作树原文件。[宿主并发修改回执](../reports/clarke_webcore_tokenizer_review_20261126/late_source_edit.json)

从 `dca31102` 重建普通 ISO `f4a2b0112f2367c8`。QEMU 11.1.2 启动前读回 FAT 上的
目标 ELF 和页文件，分别验证缺失路径退出 2、真实 HTML 分词退出 0。两次都恢复 129696
空闲页、3 个任务和 1 条完成记录。原生重编、客体日志和 SHA-256 见
[验收索引](../reports/clarke_webcore_tokenizer_review_20261126/manifest.json)。
