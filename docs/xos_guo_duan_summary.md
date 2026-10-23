# XOS GUO / DUAN 设计稿

> 状态：讨论稿 v0.2 · 2026-10-23  
> 范围：GUO 终端人格、命令仪式、剧情门槛与 DUAN 接口契约。  
> 关系：不替代 `xos_plan.md`；GUO/DUAN 不得反过来决定 OS 架构。  
> 现状：E04 已有用户态监督/ELF 装载终端；GUO 仍只有内核 `guo` 问候、`joke`、`about`，没有 `guo>`、ls/cat 或文件系统。本稿不自动激活彩蛋支线。
> 本稿决策：单文档；保留荒诞梗、去掉脏话；DUAN 保留长线契约，当前不排期。

## 0. 一页读懂

| | GUO | DUAN |
|---|---|---|
| 是什么 | 有用但要求手续的 shell 人格 | 图形会话启动器 |
| 不是什么 | 独立 OS、权限来源、文字冒险游戏 | 桌面环境、政治角色 |
| 核心笑点 | 每个命令有固定的一个特殊参数，照做就能用 | 冷静、字面、不接 GUO 的梗 |
| 当前状态 | 只有问候彩蛋 | 未实现；长线计划，当前未排期 |

**GUO 让命令变难用，但不让命令变成假的；DUAN 让图形会话可用，但不陪 GUO 演戏。**

## 1. 现状与红线

### 1.1 已经存在的

- `xos64> guo` 只打印 Guo YePeng 问候，不切换提示符。
- `joke` 五条确定性笑话；`about` 版本与致谢。
- E04 `run` 后是 supervisor 的 `sup>`，有 ps/kill/exec/spawn/wait 等命令，仍不是 GUO。
- 没有 `ls`/`cat`/`sh`/文件系统，所以现在不能实现真实的 ls/cat 仪式。

### 1.2 红线

1. `guo --exit` 永远有效；玩笑层不改变真实命令的语义、退出码、文件内容或权限。
2. 真实错误原样显示；panic、权限拒绝和恢复路径不经过 GUO 文案。
3. 不新增包管理器、编译器、桌面环境或独立 GUO OS；所有彩蛋可用 `easter_eggs` 关闭。
4. 行为确定：不靠随机数、时间或网络决定放行；剧情阶段不授予任何真实权限。

## 2. 角色与语气

### 2.1 GUO

把系统操作解释成行政审批的影子 Shell。它真心认为自己该接管系统，但权力只存在于提示符和文案里。

- **礼貌地威胁**：用“建议”“请”“按规定”包装不合理要求，不直接骂人。
- **把技术行为说成流程**：读文件是查阅申请，编译是资源占用许可。
- **笑点落回自己**：讽刺官僚主义和 GUO 的权力欲，不嘲笑真实用户或群体。

```text
GUO: Your request has been received.
GUO: It has also been denied, for now.
GUO: Please resubmit with --please.
```

### 2.2 DUAN

D.U.A.N. = Desktop User Access Node，图形会话启动器。只做参数校验、状态查询、启动/停止会话；不可用时明确报错，不伪装成功。说话短、字面、可预测，不接笑话，也不承认 GUO 的“行政权”。

### 2.3 Developer

极少出现，只在 GUO 反复要求接管时冷淡回复：

```text
Developer: No.
Developer: Ask again after the next release.
```


## 3. GUO 的交互模型：可用但奇怪

### 3.1 进入与离开

```text
xos64> guo
Entering GUO mode.
There is no approved documentation.
Type 'guo --exit' to leave.

guo> ...
```

- 默认仍是普通 `xos64>`；只有输入 `guo` 才进入模式。模式状态只在当前会话，重启不保留。
- `guo --exit` 精确匹配，任何时候都恢复原提示符。
- 模式内不发真实命令，除非完成该命令的仪式。

### 3.2 审批式命令

除 `help` 的多步梗和 `guo --exit` 外，每个命令恰好有一个固定的特殊参数。裸命令被拒绝并提示缺什么；补齐后执行真实命令。

- 特殊参数从参数中剥离，剩余参数原样传给真实命令。
- 特殊参数放在真实参数之前；解析器只认该命令自己的参数。
- 未来命令数量增长后按 `please`/`appeal`/`bitte`/`beg` 分组，同类共享参数；当前仍逐个命令固定。
- 每个命令格式固定、可复现，GUO 内部不提供完整帮助。
- 真实命令的 stdout/stderr/退出码原样保留。
- 未登记命令暂不设计；等命令数量增长、分类规则确定后再补。

### 3.3 命令仪式表（草案）

| 裸命令 | 需要的形式 | 第一次拒绝 |
|---|---|---|
| `ls` | `ls --please` | `ls: missing --please.` |
| `cat file` | `cat --appeal file` | `cat: an appeal is required.` |
| `rm file` | `rm --apology file` | `rm: an apology is required.` |
| `cp a b` | `cp --blessing a b` | `cp: this transfer needs a blessing.` |
| `grep pat file` | `grep --justification pat file` | `grep: justify the search.` |
| `make` | `make --tribute` | `make: tribute not received.` |
| `gcc ...` | `gcc --offering ...` | `gcc: an offering is customary.` |

每个命令只有一个特殊参数；例如 `cat` 只需要 `--appeal`，不会继续要求 `--force` 或 `--letsgo`。

### 3.4 帮助的有限递归

保留 `help --help --help` 的梗，但做成有限升级，不无限卡住：

```text
guo> help
help: command not found. try "help --help".
guo> help --help
help: unrecognized option '--help'. try "help --help --help".
guo> help --help --help
<正常 help 输出>
```

第三次直接给正常帮助，不再要求更多参数。

### 3.5 `guo --debug`

`GUO: Guo itself is a bug.` 随后仍显示真实版本/构建信息；错误路径不进入 GUO。

## 4. DUAN：长线契约，当前不排期

```text
duan --start
duan --start --resolution=1280x720
duan --display=0
duan --session=default
duan --status
duan --stop
```

- 图形能力不存在时，`duan --start` 必须明确返回“不可用”，不能假装成功。
- GUO 可改自己的提示符/别名，但不能改 DUAN 的配置或权限。
- 用户可从 `guo>` 执行 `duan --start`；DUAN 不要求先退出 GUO，也不回应“新政府”。
- 自动启动必须服从用户配置和权限规则，GUO 不能绕过。

**排期：属于长线计划，当前不排期。** GUI/图形会话是未来方向，但现在没有图形栈、窗口系统或 GPU 支持，所以不设日期、不先搭空壳；这不等同于取消 DUAN，等图形能力真实存在后再开实现任务。

## 5. 剧情阶段：跟随真实能力解锁

| 阶段 | 真实能力前提 | GUO 行为 | 计划 |
|---|---|---|---|
| STG 0 | E03 内核控制台 | 问候、joke、about；没有 `guo>` | E03 已完成 |
| STG 1 | 用户态 shell 与命令分发 | `guo>`、仪式、`--exit` | E04–E05 |
| STG 2 | 文件系统与配置持久化 | 保存主题/提示符/语言 | E07 |
| STG 3 | GCC/G++ 可用 | `guo-cc` 别名与命名权笑话 | E08 |
| STG 4 | TUI/终端配置 | `cus-tui` 主题、提示符、语言 | E09 以后 |
| STG 5 | 图形会话可用 | DUAN CLI 与 autorun | 长线（D04，当前未排期） |

- 阶段是剧情门槛，不是版本号；能力不存在时只能说“条件不足”。
- `guo --takeover` 只检查能力并播放文案，不授予权限；`--stg=N` 只是预览。
- 条件不足：接管失败，GUO 移出当前会话；用户数据不受影响，可经正常安装路径恢复。
- 条件满足：GUO-OS 是永久的提示符/文案化妆层，不是第二个 OS；命令保持正常，只保留 `guo-os>` 外观。
- 再次要求接管时 Developer 冷淡拒绝，不写脏话，不扩剧情分支。

## 6. 实现切片与验收

| 切片 | 时机 | 范围 | 验收 |
|---|---|---|---|
| A. 设计定稿 | 现在 | 本文、命令表、台词 canon | 决策项关闭；不与 E03/E04 冲突 |
| C. 用户态 GUO shell | E04–E05 | 真实 ls/cat/grep 与仪式 | 仪式逐条测试；错误透传；可关闭 |
| D. 持久化 | E07 | 主题、提示符、语言、仪式偏好 | 重启恢复；坏配置不阻断启动 |
| E. 工具链梗 | E08 | `guo-cc` 指向真实 GCC/G++ | 不维护第二套编译器 |
| F. DUAN | 长线，图形能力后 | CLI、状态、失败语义 | 不可用时不假成功；不改 GUO 权限 |

现阶段只保留 `guo` 问候；不在内核终端实现模式或仪式，等用户态 shell 到位后再做切片 C。

共同验收：`guo --exit` 始终有效；stdout/stderr/退出码不被改写；真实错误/panic/权限拒绝不被覆盖；不新增权限或后台服务；行为确定且可关闭；有 smoke 或手工记录，未运行项写明“未运行”。

## 7. 非目标

- 不做完整文字冒险、任务/成就系统或大量剧情分支。
- 不维护独立编译器、包管理器、桌面环境或第二个 OS；不为梗提前建子系统。
- 不让剧情授权，也不让仪式阻塞退出、恢复、panic 报告或紧急控制。
- 不使用脏话、人身攻击或真实政治/宗教隐喻。

## 8. 已定与待定

- 未登记命令：当前不特殊处理；等命令数量增长后按 `please`/`appeal`/`bitte`/`beg` 分类，具体映射到时再定。
- `guo-os`：永久化妆层，只改提示符/文案，不影响正常命令。

## 附录：命名表

| 名称 | 含义 | 约束 |
|---|---|---|
| GUO | 影子 shell 人格 | 名字来自朋友 Guo YePeng；不赋予真实权限 |
| DUAN | 图形会话启动器 | 不参与权力斗争，不承担完整桌面 |
| Developer | GUO 的“上级” | 少量出现，冷淡，不骂人 |
| `guo-cc` | GUO 环境的编译器别名 | 指向真实 GCC/G++，不是新编译器 |
| `guo-os` | 永久的提示符/文案化妆层 | 不是第二个 OS，不改内核，不影响命令 |

> GUO wants to govern the system. DUAN just starts the desktop. XOS remains the actual operating system.
