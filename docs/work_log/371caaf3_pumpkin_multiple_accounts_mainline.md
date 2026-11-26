# 371caaf3 · Pumpkin 多持久账户主线复验

从已合入 FAT 导入的主线 `492f37ea` 重建测试镜像 `6a59513e11ba3742`。
QEMU 11.1.2 使用旧镜像 `b520b0ee54972dd2` 发放 Alice 的原钱包；新镜像
读取原钱包并在同一安装登记 Carol。客体完成全部 23 项检查。
[主线客体回执](../reports/pumpkin_multiple_accounts_mainline_20261126/accounts.json)

两个账户具有各自的完整持久 ID。真实登记端切换同名资源归属后，独立 broker
依据现有认证会话和当前对象键允许相应所有者读取，拒绝另一账户、旧键及注销后
未到期的待用读取。吊销 Alice 后 Carol 仍可读取。吊销 Carol 后新 VM 拒绝 Carol
的原凭据。另一次空安装从非 Alice 的首账户启动并跨重启恢复。

本次还重建了独立原生登录配置 `9087776f6a2c6e1f`，通过创建、健康恢复与旧盘拒绝。
兼容范围包含原钱包文件和盘外代际格式，账户选择走开发配置的既有受信输入。
生产凭据交付、物理独立代际、掉电恢复和并行桌面会话各有后续验收门。
[原生登录复验](../reports/pumpkin_multiple_accounts_mainline_20261126/legacy_native.json)
