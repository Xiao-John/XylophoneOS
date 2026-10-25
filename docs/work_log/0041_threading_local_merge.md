# 0041：多线程PR与本地B2/ISO整合确认

2026-10-25。用户已review/merge多线程PR，要求拉取本地；随后明确暂停dash B2、
先确认合并。远端main从9c896df快进至d89d1a3（1:1线程实现与SDK）。本组不执行
用户随后计划的回滚/新Release，不修改CPython源码，不继续xpm功能开发。

## 保存与合并

合并前保存tracked二进制patch/摘要到.cache/xos_seed/integration/的本次目录，
Git可恢复引用refs/xos-backups/pre-threading-merge；再执行
`git merge --ff-only --autostash origin/main`。Git快进完成，autostash恢复本地改动时
有4文件冲突：tasks.cpp、newlib_syscalls.cpp、file_client.cpp和decisions.md。
手工整合后无unmerged entries；原本未暂存的改动恢复为未暂存，保留所有工作树
文件和autostash恢复材料。没有commit/push本地ISO/B2/游戏/CPython/xpm未完成内容。

## 关键整合

- 保留远端线程sys38–52。未发布ISO的sys_boot_payload从38改53；共享头、kernel
  dispatcher与使用符号的supervisor调用方一致，避免38被线程入口提前截获。
- Escape从监督线程的process wait出发，沿进程及其blocked process-wait线程找
  前台链末端；保留B2嵌套取消，适配新的process_record/thread_record。
- files枚举使用process_record，并保留B2需要的building会话转交；线程TID不变成
  文件会话身份。Client新增seek-origin/transfer也使用PR的进程级session_guard。
- POSIX spawn的顺序file actions应用到私有FD快照；临时打开对象随快照清理，
  引用原对象保持pin，不把B2的临时操作写进多线程共享FD表。保留真实handle
  转交，禁止退回按路径重开模拟共享偏移。open对象不再使用B2已移除的position。
- ISO/make disk预装dash、新引导代码及其他本地改动保留；没有替用户回滚它们。

## 验证

隔离build/thread_merge_check构建成功，build660723db5e2b005e，kernel.bin360508字节。
镜像SHA256 629f4c6fe4dd02c7b55de7d5576d3e1555d2b6317553ec0872e747ab859a91e1。
隔离SDK重建dash B2，SHA256
474abe7ba496fd19fd927a5ce522855e67c0561ab6a2c5c9aeab224b58b42c19；manifest在
.cache/xos_seed/dash/cf96062e213ed8052cb1/。没有重建/覆盖共享build镜像和日常盘。

构建命令为在scripts/build.py模块中将BUILD指定到build/thread_merge_check后main；
随后：

```sh
python3 scripts/build_dash.py --sdk build/thread_merge_check/sdk
python3 tests/thread_merge_smoke.py --system build/thread_merge_check --dash-manifest .cache/xos_seed/dash/cf96062e213ed8052cb1/manifest.json
```

新增7组整合检查全部通过：thread core（TLS/栈/FPU/抢占/回滚/join/等待等）、last
线程清理、最后线程仲裁、spawn私有快照顺序动作、B2共享偏移/重定向顺序/内建恢复、
嵌套Escape、ISO sys53安装dash并进入/退出dash。前6组每组资源恢复[129833,2,0]。
ISO SHA256 76be8c5d043728b87a40c2f70e778f4216b9c611343be6ebcf12600c41a703bd。

第一次编译发现自动合并残留position写入，删除后通过；第一次整合runner在前6组
通过后漏传ISO打包器--kernel参数，ISO尚未运行。修正runner后以--iso-only只补
第7组，复用前6组同一镜像/同一dash的证据，不重复已经通过的客体项。
merge_report.json、merge_receipt.json、build.log和串口在隔离目录；93份相关内核/
共享/用户源码摘要与实际构建回执一致。主代码无未解决冲突，普通源码diff检查通过。

本轮不重跑远端PR完整T2 SDK/newlib/libstdc++资格测试，不将其旧SDK回执改绑到
本地新source。远端原始资格材料见docs/reports/threading_20261025/。B2的完整GNU
编译链/正式收口仍由其负责人继续；不以本次整合7组冒认B2或所有Shell能力已完成。
没有旧压力/全量回归、新发行或第二ISA启动声明。

## 交接

本地HEAD=d89d1a3；当前B2/ISO整合调整在工作树，未提交。本组源码编辑/隔离构建
占用解除，dash B2按用户指示仍暂停，是否恢复由用户安排。接续时直接使用当前
文件，不再stash pop覆盖它们；新SDK以新manifest绑定，旧SDK/CPython回执保留。
文件wire版本仍2、布局兼容，B2新增操作append；不要擅自将wire改3而打断已有静态
工具。xpm P1宿主10组已过，原生只读xpm/dash双Shell客体gate尚未完成，仍待后续。
localpilot未读/改，日常盘/冻结发行附件未动。
