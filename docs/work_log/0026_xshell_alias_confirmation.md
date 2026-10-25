# 0026：确认Xshell的exd与PATH

2026-10-25，用户要求确认另一任务新增的临时exd别名与/usr/bin搜索已经完成。
本组只读核对实现并做定向客体验证，没有修改Xshell或扩展语法。

确认exd与exec-driver进入相同分支、grant_spawn=true；固定搜索路径为
/usr/bin:/bin:/，并以PATH环境变量传给孩子。不是通用alias内建或可配置PATH赋值。

测试前核对当前manifest与supervisor.cpp、file_ui.cpp、file_ui.hpp、files.cpp
实际源码摘要一致，xos.img摘要一致。系统build 498ad82e530fbf23。
隔离512MiB临时盘仅安装dash、hello与小脚本，未改日常/发行工作盘。

四项通过：

- exd dash /tests/launch.sh：通过PATH找到dash；脚本再次通过继承PATH启动hello，
  输出hello from file及inherited_path=</usr/bin:/bin:/>，确认driver构造权真实有效。
- dash -c true：裸命令PATH启动并正常退出。
- exec-driver dash -c true：原命令仍有效。
- exd /usr/bin/dash -c true：别名接受显式路径。

各项退出0，资源均回到[130342,2,0]。串口build/xshell_alias_confirm_serial.log，
报告.cache/xos_seed/dash/xshell_alias_report.json；临时验证脚本在同目录
verify_xshell_alias.py。没有重跑dash全量16项或历史压力。

0025中“并发Xshell PATH修改未验”的历史说明保留；该行为现由本记录独立确认。
dash仍是从原生Xshell启动的可选程序。本组完成，无源码编辑占用，未提交/推送。
