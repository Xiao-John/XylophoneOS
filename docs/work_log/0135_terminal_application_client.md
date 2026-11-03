# 0135：应用终端客户端基础

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-30。增加 SDK 单请求应用客户端，显式接受启动者提供的 supervisor 和服务
PID，并枚举通道、核对内核认证的控制者/对端/方向；不存在、重复或不匹配时拒绝。
读写最多 256 字节并保留短结果，验证响应序号及长度，非零请求不把零响应误作 EOF；
传输或格式错误关闭会话，已发请求的结果可能未知。接口及边界见
[终端控制契约](../contracts/terminal_control.md)。没有改变内核 ABI。

`c++ -std=c++20 -Wall -Wextra -Werror -I src/shared/include -I src/user/include
src/user/sdk/terminal_client.cpp tests/fixtures/ncursesw/terminal_client_host.cpp
-o ${XOS_SCRATCH}/xos_terminal_client_host && ${XOS_SCRATCH}/xos_terminal_client_host` 通过；模拟覆盖身份
不匹配、有效连接、读写短结果和错误长度关闭。`python3 scripts/build.py --output-dir
build/w1_terminal_client_20261030` 通过，build ID `eddf8404f54af210`。
构建早于本记录文档更新；`git diff --check` 通过。未运行客体。

启动者目前尚无向应用可信传递会话身份的启动页接线；libc 和 stdio/termios 也没有
使用该客户端。须处理 building 阶段创建通道、启动失败清理、成功/失败 exec、fork、
前台恢复和错误路径，不能把此 API 当成 W1 或 W2。所有相关改动提交后才能验收。
