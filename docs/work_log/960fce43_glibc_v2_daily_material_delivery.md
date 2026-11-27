# 960fce43 · 同版发行日用程序重链接归档暂存

日用程序可以随既有 glibc 上游源码、xypm 和 Dash 对应材料一起暂存。入口
复用逐成员校验，并绑定实际 daily XPK、候选发行清单、SDK 清单和应用 profile。
外层清单 v4 记录日用重链接清单和实际构建回执的摘要。

在 [Dash 暂存命令](960fce43_glibc_v2_dash_material_delivery.md) 的其他参数
不变时增加以下两个参数。

```sh
--daily-relink "$DAILY_TAR" --daily-manifest-sha256 "$DAILY_MANIFEST_SHA256"
```

断网 Linux 以真实 `960fce43` 发行实物重跑。新增日用程序归档 8,464,546 B，
原字节 SHA-256 为
`144dda7ee48f140c631a9788d9540c5227ef01be50c74873ff105f5f13405710`。
独立目录按外层校验表核对 13 项，省略日用参数时重现此前的 v3 结果。
错误清单摘要、外来 daily XPK、错 profile 和单个已篡改链接对象均被拒绝。
[实物清单与核对](../reports/glibc_v2_daily_material_delivery_20261127/manifest.json)

归档与实际客体验收使用相同 13 个 ELF 的非 libc 对象。断网接收方逐字节复现
XPK 的 13 个可执行成员，替换版按盘上相同路径从 Dash 运行并检查正常输出、退出标记
和资源回收。
[13 个程序的替换客体与重链](960fce43_glibc_v2_daily_relink.md)

此提交只更新候选暂存。CPython、GNU Make 和冻结编译器供体仍按各自流程验收。
