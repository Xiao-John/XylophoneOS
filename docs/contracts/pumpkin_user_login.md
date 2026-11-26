# Pumpkin 用户凭据的领取和提交

显式 `--pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login` 构建专用开发入口。它复用真实 Pumpkin 守护进程、files 私有槽和独立宿主代际，由每个账户的持有者管理自己的宿主凭据文件。同一安装可以登记多个持久账户，沿用核心的 64 账户上限。`--account` 选择区分大小写的 1 到 32 字节账户名，省略时为兼容选择 `alice`。[原生凭据链](pumpkin_native_login.md)

## 启动和使用

```sh
python3 -B scripts/pumpkin_user_login.py prepare --state "$STATE"
python3 -B scripts/pumpkin_user_login.py enroll --system "$SYSTEM" --state "$STATE" \
  --credential-file "$PRIVATE_CREDENTIAL"
python3 -B scripts/pumpkin_user_login.py login --system "$SYSTEM" --state "$STATE" \
  --credential-file "$PRIVATE_CREDENTIAL"
python3 -B scripts/pumpkin_user_login.py revoke --system "$SYSTEM" --state "$STATE"
```

`prepare` 创建启动实例使用的私有目录、带隔离尾区的虚拟工作盘和盘外代际记录。每次登记、登录或吊销启动一个新的虚机进程。首个账户在修订 2 确认后交付凭据，后续新账户先恢复已发布账户库，再推进一个修订。登记端先核对名字未使用，确认宿主已独占预留凭据文件后才创建账户。重复登记即使给出新路径也不会创建新的凭据文件。状态明确后同步凭据文件和目录。登录读取用户选定的文件，在普通权限下建立身份会话，核对持久账户身份，执行正常登出并确认原会话失效。退出码 0 表示指定操作已完成，3 表示实际普通认证被拒绝，1 表示操作失败或未确认。管理员通过受信启动配置和安装状态选择要吊销的账户。吊销仅使该账户的会话和凭据失效。

凭据文件沿用 `PUMKEY` 的原 64 字节记录，含格式、账户安装域和编号，以及 sys63 生成的 32 字节凭据。旧用户在原安装上继续使用原文件。登记库才负责把名字解析为完整账户 ID。宿主核对选定钱包在此 ID 下匹配后才发送凭据。工具通过 `openat` 的文件描述符接口打开或独占创建最终文件，在实际描述符上核验所有者、0600 权限、普通文件类型、单链接和长度，再完成读取或保存。符号链接、公开权限和多链接拒绝。一旦已经开始登记，未收到确认或写入失败不自动重复登记。保留原状态先确认账户记录，再由受信登记流程显式恢复或轮换。空、残缺或长度错误的文件不能提交。

## 私有输入路线

普通终端的前台和回显状态无法认证提示来源。此入口在启动监督器把 COM1 独占交给内置代理、关闭旧调试路径后才交接凭据。宿主程序拥有专用 QEMU 输入输出管道和私有 QMP 套接字，丢弃交接前启动文本。安装使用配套的操作者协议 2 构建，加入两个固定 144 字节的无秘密 `PKO1` 交换。第一个在进入 daemon 前确定操作和账户名字，盘外记录为空时只有登记可启用初始化。第二个只在确认待登记名字未用后请求宿主预留钱包文件。凭据发布或提交帧沿用 `PKU1` 版本 1 和精确账户身份，`PKA1` 仍只传代际元数据。每次虚机运行最多交换一份凭据，代理与受信监督器在交付后以等长无秘密帧覆盖双方暂存邮箱。专用管道无需共享串口录制、网络或调试器。

登记端来自真实父进程的既有授权。提交时，真实启动者只向经过双方内核端点验证的内置独立持有者转交凭据。持有者核对 daemon 对端，通过普通 Pumpkin 连接向核心发起真实认证。成功或拒绝后清理用户态工作缓冲，按既有会话生命周期回收。凭据全程不进入启动参数、共享串口录制、客体 FAT 明文、日志或验收报告。宿主文件由用户自行保护，具有同一宿主 UID 权限的程序、宿主管理员和虚拟化平台属于该配置的信任边界。

本配置依赖受控宿主、固定启动镜像和旧有盘外代际来源。物理控制台的可信指示、物理独立代际、用户凭据文件的加密保管和全系统内存残留审计仍待分别验证。公共内核 ABI 和默认启动无变化。 [盘外代际](pumpkin_anchored_guest.md)

## Mobius 登录

加上 `--pumpkin-mobius-elf "$MOBIUS_ELF"` 构建专用桌面登录镜像。构建记录固定该 ELF
的尺寸与 SHA-256。用同一 ELF 在准备好的私有工作盘安装 `/usr/bin/mobius.elf`，
先通过原有 `enroll` 命令取得凭据，再启动桌面登录。显示后端由受控宿主选择。

```sh
python3 scripts/pumpkin_user_login.py desktop --system "$SYSTEM" --state "$STATE" \
  --credential-file "$PRIVATE_CREDENTIAL" --display "$QEMU_DISPLAY"
```

持有者在普通 Pumpkin 连接上核对完整持久身份，随后在启动者已验证的私用通道报告就绪。
启动者委托既有 Display 服务并启动 Interactium，核对会合对象的内核对端。Mobius 从同一
只读 pin 校验并装载，按普通进程权限运行，启动参数只含程序路径。凭据、会话号、身份和
登记端在各自受信进程内。宿主在一次私有发送结束时立即清除自己的钱包工作副本。
运行阶段监督器约每秒让持有者重新向 Pumpkin 核对身份。
会话随原连接到期，桌面结束和认证中断均触发所属进程回收。正常关闭桌面后，持有者执行
注销并验证旧会话失效，启动器复核页、任务和完成记录恢复后才确认成功。当前入口使用
Mobius 单窗口桌面，应用切换及面向桌面应用的对象委派留待专项验收。

### 管理员吊销活动桌面

受信宿主可在 `desktop` 命令上显式追加 `--revoke-on-signal`。启动工具公布自己的
进程号。管理员在确认桌面已经出现后，从同一宿主账户给这次仍在运行的工具发送
`SIGUSR1`。信号权限由宿主操作系统校验。该开发配置已经将同一宿主账户和宿主
管理员纳入信任边界。宿主进程独占本次安装目录，所选账户固定为这次桌面登录身份。
未收到管理信号时，用户可照常关闭桌面并注销。

监控循环在核对现有普通会话后，通过独占代理的 `PKD1` 私有帧读取管理决定。帧长
仍为 144 字节，序号独立递增，保留区全零。帧仅包含继续运行或吊销的决定。启用
后约每秒询问一次，沿用有界代理等待和现有会话期限。只有已收到本次明确吊销决定，
工具才接纳守护进程的一次盘外代际发布。监督器通过原有登记端调用账户吊销，释放
Mobius、Interactium 和 Display 后，让持有者在原普通端点验证身份查询被拒绝。
监督器等待持有者结束，核对页、任务和完成记录恢复。宿主复核独立记录恰好前进一代
后报告成功。此操作只作用于当前账户。持久提交结果不明时，先读回安装状态再处理。

活动吊销需要配套的开发镜像、受控宿主、已登记账户和操作者工具。生产代际、物理
控制台管理权限与应用级委派仍沿用各自的验收门。

## 可选封存资源

追加 `--pumpkin-user-resource` 在同一开发配置中加入不可变 broker 映像。使用同一
已登记的用户凭据，可以从受信宿主选择实际资源入口。

```sh
python3 -B scripts/pumpkin_user_login.py read-resource --system "$SYSTEM" --state "$STATE" \
  --credential-file "$PRIVATE_CREDENTIAL"
```

普通 `login` 继续按原规则认证和登出。资源入口复用私用串口提交消息和现有
持有者。持有者先在其普通 daemon 端点认证，再核对会话所绑定的完整账户身份。
启动监督器在自己的真实登记端读取已持久发布的账户身份，确认持有者成功认证后才
启动 broker。启动者将该身份和本次 daemon 代际一并用于 broker 封存对象。普通
持有者只获得用于核对 broker 的真实进程身份，文件描述和对象标签留在 broker。
读取使用 [一次读取关联](pumpkin_resource_service.md) 和当前已登录会话。

同一启动内，持有者核对实际读出的对象字节，准备第二次读取后正常登出，并确认
该待用关联在有效期内已被拒绝。监督器等持有者和 broker 均退出且资源恢复才报告成功。
每次新 VM 重建匿名封存对象，完整账户身份从持久库恢复。账户吊销后，下一次资源
入口把真实认证拒绝返回为退出码 3，且无需启动 broker。成功的读取与登出不推进
持久账户代际。宿主仍只接收结果码，封存对象字节和原生授予留在客体内。

## 可选具名资源

在封存资源所需的构建选项上追加 `--pumpkin-named-resource-store`，使用新的私有
安装目录。此组合启用 `read-named`、`publish-named` 和 `erase-named`。
用 `prepare --system "$SYSTEM" --state "$STATE"` 初始化本配置的盘外格式 2。
用 `enroll --account` 领取各自凭据。`publish-named` 和 `import-fat` 通过 `--account`
选择对象的持久所有者，由真实登记端从恢复的账户库解析。`publish-named` 和
`erase-named` 需要受信操作者对安装目录及启动配置的管理权限。

```sh
python3 -B scripts/pumpkin_user_login.py publish-named --system "$SYSTEM" --state "$STATE" \
  --account carol --resource-name preview --generation 0 --resource-value 293
python3 -B scripts/pumpkin_user_login.py read-named --system "$SYSTEM" --state "$STATE" \
  --account carol --resource-name preview --credential-file "$PRIVATE_CREDENTIAL"
python3 -B scripts/pumpkin_user_login.py erase-named --system "$SYSTEM" --state "$STATE" \
  --resource-name preview --generation "$CURRENT_GENERATION"
```

发布时预期代际 `0` 要求当前为空。替换和删除均提交实际已有对象的确切代际。
读取可附加 `--generation` 以固定预期对象。一次提交保存已持久登记账户的所有者、
对象数据和新的对象键。成功读取返回代际及有界对象数据，退出前真实持有者完成
登出并复核有效期内的待用读取被拒绝。退出码 4 表示无匹配对象或未获对象权限，
5 表示变更的预期代际冲突。普通认证拒绝继续用 3。未确认变更后先检查实际代际。
另一已登录账户选择同名同代际时仍通过自己的真实会话受检，缺少对象所有者权利时
只收到退出码 4。显式替换当前对象可以选择另一持久账户，旧键失效。

选择和结果用 `PKN1` 版本 2 帧走同一专用宿主管道。凭据仍由既有经过核验的私有
描述符和专用 `PKU1` 帧传输。监督器只向通过普通认证的持有者交接 broker 的真实
进程，broker 在受信服务间端点取得经过一次性授权的当前对象值。每次命令启动新
VM 并重新取得通道，普通封存资源通过自己的原镜像启动。[服务授权](pumpkin_resource_service.md)

受信操作者可以从现有来宾工作盘复制一个普通 FAT 文件。

```sh
python3 -B scripts/pumpkin_user_login.py import-fat --system "$SYSTEM" --state "$STATE" \
  --resource-name artifact --generation 0 --fat-source /input/public.bin
```

`import-fat` 保留 `publish-named` 相同的比较发布规则，接受 1 到 32 字节二进制文件。
读回时四字节仍输出原来的无符号值解释，其余长度返回十六进制字节。源打开、长度或
精确读取无法确认时退出码为 6。若发布回执不明确，先从已确认代际核对实际对象。
批准导入赋予的是复制后对象的归属，普通源文件权限仍由 files 的现有规则管理。
[FAT 导入边界](pumpkin_named_resource_store.md#从普通-fat-文件导入)
