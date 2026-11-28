# d9389a24 P1-D 主线整合与正式仓库兼容验收

## 完成结果

在C已合入的主线上无冲突整合冻结D，使用新的native镜像再次通过三次实际
正式仓库验收：安装generation1101/sequence1到authority revision2；升级
generation1102/sequence2到revision3；拒绝旧正式签名并保持revision3。
三轮各执行一个真实安装器和一个GNU libc应用，输出与退出均通过。

主线父提交：`a4d409695c4368a8522a15cb8565fd5905064d72`；D父提交：
`03462213d0fd950341880866971d88e76d8421eb`；共同基线：`6332527ab64e92371266363f41f3247717a3cac8`。
添加本组整合证据前的源码tree为`974c4e0fb864527694f4683a06fb3e44ed7b858b`。
采用独立worktree和无本地commit的合并，D父提交的94路径逐字节保留，
这些路径以外的主线内容无变更，因此保留G/H/K/C已有成果。

新系统build id为`48e4b5ee9477606d`，manifest摘要
`df2ab408cee5781923be51888a792dcb1a20a31f53506355397a64200cebde62`。三轮原始guest报告摘要
`8a218056a8315ce0a1f6d07636316f0b6cd11bfc5dda566f1544b140d45c6bd1`。新构建recipe/source/artifact和每次实际执行的完整输入
绑定在`docs/reports/p1d_main_integration/`，单独的flat manifest索引全部文件。

## 旧产物与新源码的关系

冻结shared GNU runtime manifest仍为
`a7a6360491bb8ebe13b85aab61be7d61d0cd26137d1f02f433d7ca908e8bd0dc`，native ABI仍为
`9dafe8ee0e45fbc1ccb00ee2362d1be5db38584553efcb8ae7a50d699cd4c849`。没有重建GNU、重打包旧kit或重新签名。
正式安装器仍为public XPK
`6e2be19d6bb1cc01c680f12a86ffbd1bd3720199c1eb69e01740d9957aa0d033`。
冻结应用和安装器使用的glibc SDK/profile不变，新native系统自己的SDK身份
单独记录；不能把不同的native系统manifest说成相同字节。

旧runtime清单的八项源内容差异逐项保留：process_abi.hpp和sdk.hpp新增可选
pipe-status查询；build_glibc_sdk.py及四个glibc port文件包含main已有sleep
工作；xos_app.py包含D自身构建接线。另有三个新增native输入。既有进程/
管道布局保持，dynamic/capsule/catalog/publisher四个身份头完全相同。
本组实际证明冻结GNU产物在新native镜像上兼容运行，不据此给新shared
sleep API、shared fork或重新构建的GNU库授予资格。

原D的68份证据、两份原始运行报告、已签metadata、安装器、runtime产物与
交付包等100项冻结输入完成before/after摘要核对。原八次boot仍是原报告的
八次；这里另加三次，不修改原qualification或原kit。旧包SHA-256仍为
`31db15ce0320405657fa75deadf33b2f1aa247ff2da7a2abbd8c070d0a86f0e5`，5,701,429bytes。

## 执行与边界

新系统由原D的`build_xypm_distribution_guest.py`从整合源码创建隔离snapshot，
保留production代码，只按既有recipe加入D acceptance helper和明确profile。
使用原`xypm_distribution_guest.py --official`，实际校验原public installer、
signature、SDK/profile、generation和所有输入摘要，再运行32、35、36场景。
精确可移植命令与原日志摘要登记在conversion.json。

既有authenticated sys84控制、真实daemon publisher委派、PPR12证明、不可变
staging和单次catalog/checkpoint CAS保持。launch backing显式300秒，普通
默认30秒、每RPC5秒、staging120秒不变。旧签名只在当时有效的原生时钟内
使用；metadata到期时间为2026-11-29上海19:55:31，SDK本身不因此过期。

本次仍使用明确的COM1 developer authority，C的独立UID provider验收单独
成立。没有物理任意掉电声明，没有放宽权限、deadline或内核限额，也没有
复跑无关测试来替代这三次针对新native镜像的实际兼容检查。
