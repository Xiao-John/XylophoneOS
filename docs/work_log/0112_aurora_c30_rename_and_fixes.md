# 0112 Aurora C30 改名与评审修复（宿主侧补验）

2026-10-30。按 C30（xos_plan v1.5）对 PR #29 的五个自研类名执行强制 snake_case
改名（提交 a3ae0f0，14 文件），并修复评审 8 条非阻塞意见中可修的 6 条（①②③④⑤⑧；
⑥为集成期冲突、⑦由 C30 改名解决）。冻结证据与历史 work_log 不改写、不重绑。

验收补件见 [aurora_c30_rename_20261030](../reports/aurora_c30_rename_20261030/README.md)：
改名经词边界规范化证明为纯标识符替换（14/14 字节可复现）；宿主侧编译检查 10/10，
ssg 差分夹具真跑 13/13（含新增 stale_generation_since_resets），scope 审计、
mock 语义探针、docs/ABI/whitespace 检查全过。修复③（now_ns 纳秒精度、起点改
进程内基准）与④（自定义按钮文字配色）为行为变化，客体 QEMU 套件在本机不可重跑
（Qt 目标构建树/SDK 镜像在作者主机），再验收义务记录为 NOT_RUN，不冒称通过。
