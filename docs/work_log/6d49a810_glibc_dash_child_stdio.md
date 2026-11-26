# 6d49a810 · glibc dash 外部命令管线与重定向

glibc dash 预览通过当前 `pipe2(O_CLOEXEC)` 创建管线。每段用于标准输入或
标准输出的端点通过 `dup2` 进入子进程启动快照。保存的描述符及其他临时端点
保持 CLOEXEC。启动快照保留实际打开描述，直至加载器提交或撤回。方向匹配的
阻塞管道由现有 `sys_process_stdio` 挂到子进程的 0/1/2。Shell 先启动各阶段，
随后等待并收集状态。中途启动失败会取消并收集已经启动的直接子进程。

普通文件、追加写和密封 here-doc 沿用 files 的有权句柄转移。接收 ELF 须通过
加载器的 `.xos.exec` 校验。文件别名保留服务端偏移和追加行为，Shell 的临时
描述符在命令结束后关闭。打开 here-doc 恰好占用目标标准描述符时，Shell 在
封存后显式清除该描述符的 CLOEXEC。加载器沿用调用者的创建权限和既有 files
会话规则。

预览范围为前台、至多四段的简单外部命令管线。管线阶段使用字面参数及可直接
处理的重定向。短读、EOF 和提前关闭读端的 `EPIPE` 使用原生实现。子 shell、
命令替换、后台作业、进程替换及异步信号仍需各自的运行时支持。

## 验证

[客体门禁](../../tests/dash_glibc_preview_guest.py)逐项验证完整管线内容、
`pipefail`、提前关闭读端、关闭标准描述符后的再使用、命令缺失后恢复、
文件混合管线、追加、stdout/stderr 文件别名、密封 here-doc 和接收资格。
每次普通启动检查真实子进程退出码和资源回收。客体 sync 后导出文件，
逐字节比对 10,037 字节的管线输出及各重定向文本。

最初的组合脚本把多批静态 ELF 启动放在 40 秒内。带诊断构建在延长的窗口内
完成同一混合子用例的 ELF 资格检查、文件句柄转移和完整读写。最终门禁将
管线、状态、混合文件及关闭描述符分开计时，并使用普通构建。

| 验证输入 | 实测绑定 |
| --- | --- |
| 普通系统 `a40561e1b6fb6b26` | ISO `1981e7bedd41ae612ff5b5e04f19de5123d4dfe76b929ae072e482b7c69c52c6` |
| 签名校验的 glibc 2.44 C SDK | Manifest `650f51dc62f3dfcc82db747c970f31141221515d687b70388ec9e7e43328c66a` |
| glibc dash 候选 profile | `40b3bce05074211512ad5a816af8ec80bff0e670853b48944d0f91ecdec803cb` |
| 显式安装的 glibc dash ELF | `433f35949c2f746262bd3b9d7c2899e29b74a648db976cda949a227577b96079` |
| 默认 ISO 内的 newlib dash | 与基线逐字节一致，SHA-256 `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| C SDK 压缩包 | `f91fe79cdb63d374efccf3f1e1e560c58bcde4a6515768dd62389ab532230d4d` |
| 流读写验收 ELF | `6cd50444b4a5fb7ea9a1ec7eb001a70a527c166a4565c57159e860ba8733fec3` |
| QEMU 11.1.3 | xsh 和原有 dash 入口各 20/20，报告 `73347013327fe48d87543116953c2a5c9aa187970fe27e80f6d71a1d4950e069` |
| 资源回收 | 40 个用例全部恢复至 `[129698, 3, 1]`，FAT 保留名集合为 `{}` |
| 文件校验 | 混合管线及追加输出逐字节相符，现有 newlib dash 实际接收文件流，未声明接收资格的 ELF 返回 126 |
| 宿主回归 | 49 项文件运行时检查、15 组真实 files/FatFs 组合检查及管线描述符恢复通过 |

## 内建 here-document 与路径变更合流后

从 `90d5adc81559228911b4ff264411526f42ef838c` 重建普通系统及签名 glibc C SDK。
组合同时包含后续的内建 `printf` 管线案，两个入口各通过 21 项。允许的内建和原生
外部命令都验证前置赋值前的 here-document 展开，外部路径另核对真实 stdout/stderr
文件。每项恢复 `129698 / 3 / 1`，保留 FAT 名集合不变。普通路径变更 2 次、
管道 2 次、启动等待与回收 6 次亦通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `80b164b2277c9b9b` 清单 | `b0d84d6ad40dcb9afe4ed8443faabee94f68c2e1533d402f370667a85e026a5e` |
| 系统 ISO | `0a1aae0a324ca2858fbb8014e063c62b17728de2f292b8b81a1f8f234d8ab9bb` |
| glibc C SDK 清单 | `61e9f2864a50d61c2fbc43c964909f4e07f526aa6184f8d9a7eda9e5c471f54a` |
| 显式 glibc profile | `c68e5e4cf59acfacfd75302033d2584cd02b8228be59c79d813fbfa2d6f510fc` |
| dash 双入口报告 | `dd98a596707fcaf305faf0defecbfb4fb1bfa19ff70bdc262998cf4266524e57` |
| 路径、管道、进程报告 | `0216bb489fbccfa4d043a35a2af7b3bde13df8bf92b4cd8a4fa1d508fb57a681`、`53ed724f611c959e37c58405e85e8aaf42710e96cbda6a148b4326cc305af4be`、`7c1a2d2fc4284c49524b11115e3708e0ff849a9d089a53270575d9efb5f9b257` |
