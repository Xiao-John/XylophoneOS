# 0390b1b4 · WebCore 的 LibXml2 CMake 发现复验

在 #282 的 `61d2cbba` 上用 CMake 4.4.4 的真实 `FindLibXml2` 重现审查意见。
原夹具通过单路径检查，遇到同一目标 include 目录重复出现时拒绝。现先去重，再按
同一目标归档和目标头路径核对。新增回归在默认发现之后重复目标路径，以及分别追加
前缀外路径，结果分别通过和拒绝。 [发现回执](../reports/clarke_webcore_libxml2_review_20261126/discovery_review.json)

对 `0390b1b4` 原生交叉重编 LibXml2 与探针，重新构建普通 ISO `dde02bd84f21aaac`。
QEMU 11.1.2 重新核对 FAT ELF、分块 UTF-8 正常路径和失配结束标签，分别返回 0 和 2。
两个进程均恢复 129696 空闲页、3 个任务、1 条完成记录，声明材料检查通过 10 项。
[原生构建与客体索引](../reports/clarke_webcore_libxml2_review_20261126/manifest.json)
