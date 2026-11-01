# 0132：终端发送等待

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。为 shell 后续接管补充用户态终端 `write_until`：UART 暂不可写时，驱动
启用 THRE 中断，服务用与接收共享的等待字等待 IRQ、截止或控制中断；IRQ 处理先
禁用 THRE 再应答，后续需要时重新启用。成功返回实际短写数量；控制端新增最多
256 字节的 read/write 辅助函数，检查应答长度，不将短写或未知结果伪装成完成。
专用 supervisor 探针输出改用该接口，试行边界见
[终端控制契约](../contracts/terminal_control.md)。未改动常规 Xsh 或应用 stdio。

宿主服务模拟覆盖发送空闲超时和发送就绪唤醒，原有读取/中断与控制客户端模拟通过：
`c++ -std=c++20 -Wall -Wextra -Werror -pthread -I src/shared/include -I src/user/include
tests/fixtures/ncursesw/terminal_service_host.cpp -o ${XOS_SCRATCH}/xos_terminal_service_host &&
${XOS_SCRATCH}/xos_terminal_service_host`；控制客户端探针的编译命令见 0125。
`python3 scripts/build.py --terminal-supervisor-probe --output-dir
build/w1_terminal_write_wait_20261030` 通过，build ID `2bb2bbfd53ca2095`，终端 ELF
SHA-256 `ea6a8ad46f5d6ff090507fc59d0274db19ebdbdb82b65acacb007fdff27e80b5`。
`git diff --check` 通过。构建早于本记录的文档更新。

尚未在客体验证 THRE 边沿/电平、与接收 IRQ 竞争、超时后重新使能、硬件短写、
异常恢复或发送线程唤醒；宿主模拟不能替代这些验证。下一步完成 Xsh/应用会话和
stdio 路径、恢复与 ncursesw，再从全部提交源码构建独立镜像验收 W1/W2。
