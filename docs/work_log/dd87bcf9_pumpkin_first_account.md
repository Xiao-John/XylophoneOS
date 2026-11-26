# dd87bcf9 · Pumpkin 首个账户发放

在 #294 已验收代码 `f3f6ae60` 上增加受控宿主操作 `provision-first`。安装目录的原有
独占锁覆盖空记录复核、虚机执行和最终回读。宿主收到启动代理的首个账户选择提示后，
先独占打开并核验私有钱包描述符，再发出允许初始化的应答。沿用 Pumpkin 登记端、
files 私有槽与独立代际比较发布。宿主仅在对应阶段接纳空库修订 1 和首账户修订 2，
并在交付凭据前读回修订 2。账户名称只用于定位业务对象，已有受信启动和登记端继续
决定调用资格。[首次发放契约](../contracts/pumpkin_user_login.md#首个账户发放)

已有代际拒绝首次发放，包含只有空库修订 1 的中断状态。错误或不可信的安装请求不推进
代际。已有 `enroll` 支持后续登记。结果不明确时先读回代际与钱包，随后依据原有登记端
流程核对账户或恢复凭据。物理生产配置仍需由可信启动认证首次操作者，并提供普通系统盘
回滚范围之外的独立代际。当前先冻结可复用的宿主入口及其输入、持久化和失败行为。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$HEADLESS_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login
python3 -B tests/pumpkin_user_login_guest.py --system "$HEADLESS_SYSTEM" --output "$HEADLESS_OUTPUT"
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$DESKTOP_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login --pumpkin-mobius-elf "$MOBIUS_ELF"
python3 -B tests/pumpkin_mobius_guest.py --system "$DESKTOP_SYSTEM" --executable "$MOBIUS_ELF" --output "$DESKTOP_OUTPUT"
python3 -B tests/pumpkin_generation_authority_host.py
python3 -B tests/abi_doc_consistency.py
```

QEMU 11.1.2 的无桌面镜像 `bb090b77be6d7b0c` 通过 19 项。真实发放推进到修订 2，
新虚机通过普通权限认证和注销。同名与异名重复首次发放均失败，保留已选代际和凭据。
拒绝不私有安装目录及无效账户名。占用目标文件的时序测试在 QEMU 实际启动后触发独占
打开失败，盘外记录仍为空。修订 1、修订 2 回执不明确及钱包同步失败均保留实际观察
到的代际，并阻止自动重复领取。独立代际宿主检查 9 项和 ABI 对照通过。

同一提交重建的 Mobius 镜像 `26a063fd05ca8334` 通过 8 项桌面回归。真实两主题显示、
普通登录与再次认证通过。管理模式下的正常关闭在 905 毫秒确认注销和资源回收。活动
吊销在 3105 毫秒确认原会话被拒绝及回收。同尺寸改动的 ELF 继续被拒绝。
`6bd530bf` 与此次实现的本地试合并无冲突。
[镜像、SDK 与客体回执](../reports/pumpkin_first_account_20261126/manifest.json)

## #297 后组合复验

将 #298 的 `5c587882` 与主线 `9dfccbe2` 合成为 `01bf9cf1`。无桌面镜像
`b70bb236fbad9c05` 再次通过 19 项，宿主代际和 ABI 对照通过。桌面镜像
`a73d0182bebee595` 完成 4 项。普通两主题显示、再次登录和管理模式无信号注销均通过。
启动活动吊销用例时只观察到 800×600 黑屏，操作者在首帧及吊销信号前收到桌面失败结果。
此次未确认故障源。保留真实失败回执、最后的黑帧和原始日志摘要。
[组合回执](../reports/pumpkin_first_account_post297_20261126/manifest.json)
