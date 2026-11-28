# 7f23b8e4 P1-D 认证发行与批准代际安装

## 恢复检查点：尚未取得最终资格

本组在 `6332527ab64e92371266363f41f3247717a3cac8`（P1-B/P1-E 已合并）
上重建 P1-D。2026-11-28 执行环境断连后，恢复的文件系统回到了更早快照；
此前未发布的 D 工作树、SDK/runtime 与运行日志缺失。当前提交用于保存重新
构建的源码，**不是完成声明，不替代真实 guest 验收**。不生成丢失的旧报告，
不以旧产物摘要冒充当前产物。

实现范围为独立官方 bootstrap 与 EVP Ed25519 认证、原生时钟有效期检查、
受保护 sequence/checkpoint、防回退、有界 P3 dependency resolver、完整
generation/ELF 校验及通过真实限权 publisher 的 staging/CAS 安装。

正式公钥身份保留不变；正式私钥由发布者独立保管，不进入源码、SDK、包或
测试镜像。测试使用独立 `xos.test.*` 仓库和测试密钥。源码恢复后的构建与
host/guest 结果将另行实际执行并登记。

## 尚需完成

- 完成新 SDK 构建并运行已恢复的真实 guest fixture。
- 与 P1-C 的显式 publisher 查询、capsule v3 和 owner 撤销修复对齐。
- 在新建的同一 C++ SDK/OpenSSL 上重新构建安装器、GNU 动态 runtime 和
  两个实际外部应用 generation，并重新绑定准确的 source/SDK 摘要。
- 通过实际 IPC/CAS 检查正向安装、各具体拒绝原因、staging 中断、升级与
  rollback，并验证批准应用的真实 GNU libc 输出。
- 由发布者签正式 release，完成正式仓库 guest 验收、证据清单和 index gate。

恢复前诊断曾定位 fixture 的 stdio 路径继承与父 ACK endpoint 过早关闭问题；
恢复后的 fixture 将采用父进程打开并继承文件句柄、wait 后关闭父通道。
新检查已定位原先 `-5` 的可复现来源：监督 fixture 持有两个 sys81 pair，
用尽现有四个 owned endpoint，加载器无法再创建 READY/ACK pair。与 C 共用的
fixture-only sys84 控制通道显式核对双方 kernel peer 和 HELLO/ACK；生产
daemon/proxy pair、内核界限和 runtime 均不修改。仍须用新真实 guest 证明。

## 恢复后的实际检查

- SDK 开发环境内真实 EVP 认证 ordinary 30/30：
  `build/p1d-recovered-auth-host-v2/report.json`。
- 相同 production verifier 的 ASan/UBSan 30/30：
  `build/p1d-recovered-auth-sanitized/report.json`。
- P3 repository 回归 50/50：`build/p1d-recovered-p3-regression.log`。

上述 host 验证使用显式记录的 OpenSSL 3.5.9 开发快照，不据此声称目标
OpenSSL 或 guest 已合格。正式 artifact 报告会在新目标构建及 guest 验收后登记。

本组不新增 syscall，不使用 P2 全盘 maintenance，不把签名或下载成功作为
执行/网络权限。不可变路径的公共 FAT 写入与受保护 catalog 发布是两个不同
的权限边界。COM1 developer authority 和独立 UID 生产 provider 的证据分别
登记，不据正常 sync 或 host 进程中断声称任意物理掉电资格。
