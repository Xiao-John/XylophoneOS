# 0016：Qt GUI 主线与阶段扩展

2026-10-24；主agent负责本组，文档修改已完成，无其他编辑占用。

用户确认Qt为GUI主线、SDL为次选，要求扩展计划与验收。xos_plan.md升级v0.5，
保留C12的历史并新增C13；新增E13–E20和G01–G10。QtCore、QtGui/QPA、Widgets、
QML引擎和Quick分别验收；QML可在Core后独立推进，不虚构Widgets依赖。
版本/feature/线程与资源预算实施时冻结；首轮交叉构建与Qt原生重建分开记账。

同步state.md、decisions.md、architecture_and_boot.md、qt_port_assessment.md、
e08_native_toolchain_plan.md、README.md，消除仍在生效的SDL优先描述。
保留历史日志和旧决定，不改E08既有证据，不增Qt代码或第三方依赖。

验证：git diff --check通过；阶段/验收ID、依赖及方向描述静态核对通过。
未运行构建或客体测试：本组仅修改文档，全部GUI gate保持not_run；此前E08-3
构建5276ff16bb6470b0及其验收不作为本组GUI证据。

下一开发任务仍E08-4 C Seed；未来GUI开工按E13/E14拆任务，先固定配置和预算，
不得把此计划视为Qt、SDL、线程、显示或GUI已有实现。localpilot未扫描/修改，
没有提交、推送或读取凭据。
