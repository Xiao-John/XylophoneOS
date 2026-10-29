# 0088：CPython 静态 Pillow 核心与真实并发阻塞

2026-10-29，基于最新 upstream `aaec2e9`，独立 `codex/python-static-imaging`。
本工作区与构建/镜像独立；原LocalPilot main9a21ebb只读，不改日常安装或其他工作区。

完成可选 `--pillow-archive`、固定217个源文件SHA、76个上游核心C源编译、
包名 `PIL._imaging` 静态注册、原PIL包/许可证stage与逐文件回执。
没有修改Pillow源、公共ABI/内核/libc、文件身份或应用安全检查。

最终系统`ec4b7ffa0c53f5a4` / Python`d2d064e8db8332bc7d91`，两Shell单线程
真实导入/图像变换、PNG/BMP写入重开、默认炸弹防护、异常退出和回收通过。
6个核心/收集gate通过，独立宿主解码导出字节与768个预期RGB字节完全一致。
所有最终操作返回free130279/tasks2/completions0，不推绝对峰值/压力结论。

**Pillow并发仍UNSUPPORTED/BLOCKED。** 早期dash worker真实vector14在
newlib `_malloc_r` 写top chunk header，RIP4037927b/CR260cc5fc8，tid20，主线程tid17。
该次5938页精确回收；RSP未捕获。最终7个线程/原CPython/原生zlib/诊断包装有限对照
均未重现，不能清除失败或归因为已修复。未改分配器；交线程/newlib/exec生命周期负责人。

20个原依赖观察中3项导入通过：PIL.Image、localpilot_service、原protocol。
17项失败，pypdf仍缺_posixsubprocess，核心入口仍select/fcntl等阻塞，nofollow仍EINVAL。
API1.0/身份/Operator审批/UNKNOWN各自NOT_RUN；完整Core/网络/发行没有通过声明。

构建迭代曾遇错误归档路径、Setup等号解析、版本引号、嵌套object目录；均保留原始日志，
只修构建胶水。客体初次安装重复mkdir也保留。最终稳定源码重建新系统并重新实际客体验收，
未改绑初期镜像通过。全部671个系统source SHA、CPython构建器/端口与实际SDK再校验精确匹配。

[完整回执、原始本地保留位置、状态和复现命令](../reports/modern2_python_20261029/README.md)；
[实现及可选范围](../implementation/cpython_pillow.md)。私有traceback原始份本地保留，公开副本删除
私有源行并明确脱敏；普通公开日志保留原字节gzip。许可证材料检查非逐成员/发行审查。

后续：先复现并定位allocator fault；其他线继续PX3/进程/可信文件语义和N2登记，不为import造空成功。
本功能通过独立PR交维护者审查，未自批、未合并、未发布。

交付前同步上游PR #24到`169f51e`，仅两份原则文档；已阅读C28用户态驱动、C29唯一单调时基。
Pillow无驱动/计时机制改动；N2需按新原则重审，仍BLOCKED。真实测试输入仍上述冻结源码与镜像，
未将文档同步冒充运行重验。再次核对671个系统源码SHA保持一致。
