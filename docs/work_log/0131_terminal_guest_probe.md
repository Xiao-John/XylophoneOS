# 0131：终端交接专用客体探针准备

2026-10-30。新增仅供专用构建的 supervisor 入口：在独立测试盘装入终端服务后，
从真实 supervisor 授权 COM1，拟检查 IRQ 输入字节、控制请求中断、正常服务停止和
显式重新授权。探针经终端服务输出标记，不修改常规 Xsh 路径。构建参数
`--terminal-supervisor-probe` 必须使用 `build/` 下独立子目录，profile 写入源摘要
和 manifest。新增 `tests/terminal_handoff_probe.py --system <构建目录>`，要求工作树
干净、当前源码与构建清单匹配，并检查镜像及终端 ELF 哈希后才在临时 FAT32 测试盘
运行；成功只说明上述有限路径，不能作为完整 W1/W2 资格。

第一次专用构建发现真实调用 `terminal::start` 时，supervisor 静态库链接顺序使
`spawn_file_options` 未解析；调整链接顺序后专用和普通配置均交叉构建通过。
`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_guest_probe_v3_20261030` 的 ID 为 `f749071fffff698d`，ISO SHA-256
`92946657f3302ce70ae37963d7517102b6d37ff8c3f7e3dd5df0b8302202822f`，终端 ELF
SHA-256 `6b5e5407899703912e32076fe74f05cc48ce3a73017b8953e11342f7fe9f3403`。
`python3 scripts/build.py --output-dir build/w1_normal_after_probe_20261030` 通过，
ID `cbbf013d15848939`。Python 语法检查和 `git diff --check` 通过。

客体探针**未运行**：用户要求所有相关更改提交后验收，且 W1/W2 的应用会话、真实
恢复与 ncursesw 仍在实现。探针未覆盖异常退出、权限对抗、IRQ 残留与风暴、超时
竞态、资源基线或宽字符显示；其源码和输出均不能冒称已有验证结果。下一步完成
应用前台与 stdio 接入、恢复策略以及 W2，再从提交源码重建并执行相应客体测试。
