# W1–W2 与主线设备授权登记整合

2026-11-02。刷新远端主线至 `4d8dd42`，其相对本分支包含线程构建并行度参数、
设备授权 v1 登记及 sys112 第一步输入校验。该步骤明确返回 device_unknown，尚不
提供新设备能力；W1 的 sys80–83 保持独立登记，不把 sys112 预留机制误作 COM1
服务的替代实现。合并时同时保留 sys80–83 与 sys112 的 ABI 登记，以及线程 SDK
构建器的自定义工作目录保护和 `--jobs` 正数检查及参数传递。

自动合并的内核改动仅新增 sys112 分派与请求校验，仍需在提交后从组合源码重新构建，
分别运行新设备 ABI 客体探针、W1 通道/权限/终端及 W2 组合客体检查。历史报告不能
改绑或替代组合验证；本次整合尚不表示完整 W1/W2 合格或更改本地 main。

组合回归入口增加 `w1_wait_smoke.py --probe device`：用系统 manifest 校验的普通 SDK
交叉链接主线原有 sys112 负向 fixture，并在安装 ISO 与独立测试盘中运行；报告绑定
提交、系统、SDK 和 fixture 哈希。该探针只验证当前第 1a 步的头字段校验与未实现
grant 返回值，不承诺设备授予、映射、IRQ 或 DMA。提交后必须重建并执行客体。

提交 `eb2573745c009d4535b0d4a3d105ddffc3ee27f0` 后从组合源码重建：正常系统
build ID `8abccc5bdb521fdb`、manifest SHA-256
`49fccb88031df8c6dc58a964bdce09568ca13f6117bcdda79f816ba54237d41a`，普通 SDK 树
SHA-256 `c702eb591dbdd542523d4a8137955c3655a011422806a692ce7ce8eb56372a39`。
sys112、通道、终端 fork/exec、未授权 PIO、IRQ 和 pipe 客体探针均为 `passed_subset`，
报告分别位于 `build/w1_combined_{device,channel,tty,pio,irq,wait}_eb25737/`。
前四项串口 SHA-256 依次为
`2477c9a7119f944774ba1b0bd7205fac5f65e9e6666e547e4f33092451230cdf`、
`bb8e37b0464acda5b0eacf69c371ed8acadba109bcec333d01f5d734dd278c32`、
`6c71891ab4f8b918ba244d4cb43219b1fc73611a6d79d66a67a981c6326942c7`、
`b33e21beeb2102bc68e514cb13a76edd917d46db5c2bd97fade99220586a27be`；IRQ 和 pipe
串口分别为 `3d9c0542c21f2202428ef3067bf7a5269313e2f7f718a63a39514cc38c92b64f`、
`15c2080a8edf4a390b0c8e874e1600e98b5a3356f17e49c223de5be80ae44f52`。

专用 supervisor build `440870b4733996e3` 的授权 PIO、fork/exec 授权生命周期及
终端交接探针通过，manifest SHA-256
`cddea7e47538d644bd4ac2453772eaa87a5e1bb1cb8bbe30581aa636ad2301a8`，串口 SHA-256
`5d03293682c81b9a9bc0a24ebe0f469bf45475bebc61eaeb2895cdd9d6d7d9db`，报告位于
`build/w1_combined_special_eb25737/`。文档链接和 ABI 一致性检查通过。

同提交重建 UTF-8 SDK、ncursesw 与同源 terminfo，正常 Xsh 客体 W2 探针为
`passed_probe`，组合 SDK 树 SHA-256
`6a1427dd4333ea4728cb4540a70c07252242dcf7ccbe6333de314ebeeca81430`，客体串口 SHA-256
`6051b1d855f6373042f39d88c1b7675db4e549dcbac01a27ad1605ac393fffe7`；冻结的受限子集
树 SHA-256 `1490a5355b16f447e6b4bdbba4cc64a4cbcfe6184bb1f19c4860db2fafaef804`，位于
`build/w2_combined_frozen_eb25737/`。所有结果仅覆盖各回执列明的范围：完整 W1/W2、
跨时序竞争、资源压力和成员许可证审查仍未由这些子集证明。
