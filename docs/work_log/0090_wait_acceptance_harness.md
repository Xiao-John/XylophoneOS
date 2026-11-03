# 0090：显式等待的客体探针入口

2026-10-29。新增 `tests/w1_wait_smoke.py`，在调用时先检查工作树已提交、系统
manifest 的源码/镜像摘要和 SDK 完整文件集合，再交叉构建 `wait_probe.cpp` 并在
临时 FAT 工作盘启动 QEMU。探针分别检查管道超时/可读/关闭和 console 接收唤醒、
旧调用的 would-block；报告记录版本、构建、镜像、SDK 和夹具摘要。测试结束再核对
工作树、提交、SDK 和镜像，失败保留串口及失败报告。

本轮只检查 Python 语法与 `--help`；遵循用户要求，尚未执行 QEMU 或将其标为通过。
另以未提交工作树调用入口，确认在创建输出或启动 QEMU 前返回 `Commit all work before
guest acceptance`；这是守卫检查，不是客体测试。
这个脚本仅覆盖列出的等待子集，不验证前台所有权、并发关闭、异常恢复、溢出、Unicode、
terminfo、ncurses 或资源压力；输出即使将来通过也只写 `passed_subset`。

继续 W1：现有 files 会话的句柄与 `sys_file_session` 绑定专用服务，不能直接变成
任意终端服务身份认证；需补通用受控通信/设备权利并审计旧 console 直通，再处理
前台委派和模式恢复。W2 目标库及数据仍未交付。
