# P1-D 主线整合证据

C 已合并的主线 `a4d409695c4368a8522a15cb8565fd5905064d72` 与冻结 D
`03462213d0fd950341880866971d88e76d8421eb` 无冲突整合。新 native 系统
`48e4b5ee9477606d` 实际通过三次正式仓库启动：首次安装、升级、
旧签名回退拒绝。每轮均运行选中的真实 GNU libc 应用，完成 READY/ACK、
准确输出验证和退出 0。

| 文件 | 证据 |
| --- | --- |
| `report.json` | 两个父提交、三次新运行、旧产物不变及资格边界 |
| `guest.json` | 新系统上三次实际启动的完整报告投影 |
| `serial.json` | 三次原始 serial 的无损 base64、长度与原摘要 |
| `system_recipe.json` | 源快照、D fixture 接入、构建命令和 profile |
| `system_build.json` | 新 native 系统的 source/artifact manifest |
| `source_compatibility.json` | D 的94路径保留、main未覆盖、八项旧输入差异和100项冻结产物前后校验 |
| `conversion.json` | 原始回执与公开投影的各自摘要、命令与转换定义 |
| `manifest.json` | 本目录其余文件的唯一 flat SHA-256/长度清单 |

原 D 的八次 boot、68份证据和5,701,429-byte交付包逐字节保持不变。
这里新增三次兼容运行，不把旧报告或旧包重标为新主线构建。已签官方包、
安装器、SDK和shared GNU runtime全部复用，没有重新签名或重建GNU。

与冻结runtime源清单相比，新树有八项旧输入内容不同：两个native头、两个
recipe和四个port文件，另有三个新增native输入。完整差异在来源报告中；
capsule、catalog、dynamic identity与publisher bootstrap四个身份头保持原字节。
`scripts/xos_app.py`是D构建接线变化，其他七项为此前C整合已记录的main变化。
这是旧GNU产物在新native系统上的兼容资格，不是新shared sleep/fork API资格。

三个场景的持久authority分别保持revision2、3、3。新profile仍为显式300秒
launch backing、每RPC5秒、installer staging120秒；默认30秒没有改动。
这里沿用显式COM1 developer authority，独立UID provider资格仍在C单独登记，
没有任意物理掉电声明。

JSON投影只转换SDK/workspace安装前缀与排版，每份保留原始摘要；原始回执
不变。serial须先base64解码再核对原长度/摘要，外层JSON摘要另由manifest绑定。

仓库根目录验证：

```sh
python3 scripts/verify_evidence_index.py docs/reports/p1d_main_integration/manifest.json
python3 scripts/verify_evidence_index.py docs/reports/p1d_authenticated_distribution/manifest.json
python3 tests/check_public_evidence_paths.py --index --base a4d409695c4368a8522a15cb8565fd5905064d72
```

完整记录见 `docs/work_log/d9389a24_p1d_main_integration.md`。
