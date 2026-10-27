# 0056：POSIX子集契约与路线

2026-10-26。用户要求先建立契约等文档，本组只改文档，不进入实现或派工。

## 交付

- 新增`docs/posix_subset_contract.md`：Issue 8参照、自定义子集名称、C/P/O/D边界、
  实现状态词、当前基线矩阵、错误/FD/阻塞/线程/路径/能力查询规则、架构责任与证据要求。
- 新增`docs/posix_roadmap.md`：PX0–PX9、依赖和具体验收；PX4-A设计包建议为主端下一项。
- 定点更新README、xos_plan、decisions与state；修正索引中“dash C未做”的旧说法。
  未清理或覆盖既有审计、xypm、CPython改动，未修改冻结报告或release资产。

## 选择与界限

xos-posix-subset-v1是项目工程契约，不是正式标准profile或SDK ABI。当前只完成PX0文档，
不承诺全部标准选项、不宣布完整POSIX。保留xsh默认、dash可选；COW独立可选。
信号/终端、等待、映射、文件、线程/时间、工具与网络分别验收，不强制Qt等先等待全部完成。
墙钟工作树已见实现，仍按现有PY3 B2专项任务记in_progress，不将其当未开工或已通过。

## 核对与未运行项

读取Discipline、state、计划及相关C3/线程/审计/xypm记录，核对当前Shell范围和pthread
占位边界；查询Open Group Issue 8的fork、exec、信号掩码和能力声明官方材料，链接留于契约。
本次没有做标准所有条款审计，基础/选项分类待逐项核对，不填写虚假兼容百分比。

执行`git diff --check`（本组文档路径）及新增入口本地Markdown链接检查，均通过。
仅文档修改，无系统构建、新guest gate或压力测试；不复现已做过的测试。不提交、不推送。

## 接手

先读新契约和路线；若开始PX4-A，登记具体所有权，按架构/SDK入口查清映射、fork/exec、
线程等待生命期再冻结设计/ABI和测试。不得从本文推断已有mmap、信号、TTY或完整pthread。
其他线继续按state占用推进；共享build依然排他。
