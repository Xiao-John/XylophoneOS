# 0031：公共线程契约与实施计划

2026-10-25。用户确认确定契约/计划并落盘。本组仅文档，不开始线程实现。

## 已确定

新增threading_contract.md v1；E13-T提前成为公共底座，T0进程/线程分离、T1等待/
单调时间、T2线程安全pthread/newlib/C++ SDK、T3分别接CPython和Qt。
1:1内核线程、单核抢占；PID/TID与进程权限分开，线程退出不释放共享地址空间。
冻结创建事务、退出仲裁、join/detach、静态TLS与析构、进程私有比较等待/唤醒、
绝对单调截止时间与映射生命周期、pthread首版功能面及预算。syscall数值/结构
字节布局/虚拟地址图留给T0与真实ABI头同步冻结，没有假称已实现。

同步xos_plan.md v0.7/C15/E13及Qt线程段、decisions.md、cpython_port_plan.md的
公共线程前移说明、e04_loader_sdk.md的待实施引用、README索引和state.md。
原0030 CPython占用与0028交付摘要不覆盖。0028现在已交付，T0无需继续等待它。

## 核对与证据

按入口复核Discipline/state/xos_plan/相关决策/0029，读取当前任务记录、libc
共享状态、TLS析构和文件Client请求响应；它们仍为单线程实现，不能只加create。
查阅newlib重入/锁、GCC libstdc++线程配置资料；POSIX官方条件等待页直读403，
此前官方搜索摘要支持原子释放/等待语义，文档保留规范链接，不称全文已抓取。
本轮只做文档一致性、引用存在/格式及diff检查。没有源码修改、构建、QEMU、
客体gate、旧测试重跑或压力；T0–T3全部not_run，没有新build ID。
没有触碰localpilot、发布附件、日常盘或0030的源码/cache；未提交推送。

## 接手

下一组领取T0具体文件范围：先冻结ABI请求布局/映射区与兼容策略，再做创建/
退出最小闭环；T1等待底座和T2用户库按冻结接口衔接。T2才可宣称一般线程安全
SDK，CPython要再过T3-PY。公共机制由主端，移植agent继续PY0探针；没有实际
启动子agent或向其他线程发消息。规划结束，无剩余编辑占用。
