# ce9370b4 · glibc dash 内建命令的 here-document

glibc 通过已认证的 files 会话复用匿名文件 op 21 和封存 op 22。匿名文件占用最低
可用的本地 FD，初始具有 `FD_CLOEXEC`。封存成功后，原 FD 与现有别名共享只读状态。
服务继续在最后一次关闭时回收匿名文件。普通文件的封存失败保留描述符原有状态。

dash 复用原 C3 的写入、回绕、封存和重定向恢复流程。预览允许父 shell 直接执行的
内建命令使用 here-document。显式 exec、父复合语句重定向和外部命令的 here-document
保留现行能力边界。工作范围仅涉及现有文件操作和预览命令路由。

## 验证入口

[预览来宾门禁](../../tests/dash_glibc_preview_guest.py) 在 xsh 和现行 dash 两条
入口验证引用分隔符的字面内容，以及未引用分隔符内的变量和算术扩展。两条入口各
执行 24 次真实输出重定向失败，再读取新的文档，检查被中止的输入重定向已恢复。
文件回读和关机后的 FAT 保留文件清单用于核对数据及清理。

实际 files/FatFs 宿主回归验证新 libc FD 包装的 CLOEXEC、别名的封存状态、失败封存
后普通文件仍可写，以及关闭和配额恢复。

## 结果

在 Linux arm64 宿主重建签名验证通过的 glibc 2.44 C SDK 和正常 BIOS 系统。QEMU
11.1.3 上 xsh 和现行 dash 各通过 13 项。每条入口均读取了预期字节，24 次错误后
仍可读取新文档，外部 here-document 返回 2。各项资源恢复至 `[129698, 3, 1]`，
关机前后的 FAT 保留文件列表均为空。48 项宿主检查、15 组真实 files/FatFs 集成和
dash 管道描述符宿主回归通过。

普通 newlib dash 与冻结版逐字节一致，SHA-256 为
`94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067`。
在预览较新时构建普通安装镜像，仍选中该 newlib ELF。

| 验证绑定 | SHA-256 |
| --- | --- |
| 系统 `5093805c0a926466` 的普通 ISO | `3cd882344798fb043ef797f40a36d8a2d7d59806c5ef1f18f34cabac03580bee` |
| glibc C SDK manifest | `48d0013a6c11b53687197507773a55276fef717acf0b1ad2ee92ce33eb7957d7` |
| 预览 ELF | `f3c64d4aa10f197b6b73fc98cac93f3c11210a1406c22e6b14f52ca949a33c44` |
| 普通安装回执 | `c60d5456cf55f61dc8e65494948d84be619f320f7de2cb284f801c8417bba3ee` |
| 来宾报告 | `926c86272d238f8d72287faf435e53a9ef0db51cb866aa8720330eef7d24c8b8` |
| 串口 | `c4885d6b12326e8973c6421911552df684f0df61912f3ae55a4b946c1985b73f` |

## 进程锁合入后的复验

同步 `ff21348b` 时保留了匿名槽和 cwd 序列化使用的操作号。从 `e8659ae8`
空目录重建正常系统和签名 glibc C SDK，QEMU 从 xsh 与 dash 合计通过 26 项，
每项恢复 `129698 / 3 / 1`。原生 files 宿主测试和 15 组实际 FatFs 通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 manifest | `b4d447ea866fd8d98a531c2053960de7944f5533c24c1a6915dd13a24de8aa16` |
| 系统 ISO | `66a72e419ac0f833ec313bb1c760f5b98f339ec0fc115ddd5c2ae54b1266341d` |
| glibc C SDK manifest | `d036a1c56ce3dfae3a76b8ed27fbce65fbbd9c4a7262a5df50b1e340952dc959` |
| glibc profile | `f0323f7fef660bc36e55422c96bec6f589df50d675c3d5f87df64613f234a05a` |
| QEMU 回执 | `48e76f088b7466ea121cedacf8dd7bb2eafb1dedd657d3c2d4eb2bff3b591ec0` |
| 宿主回执 | `dce103452bf68e8e1c1bcd3107b736aacdd846a89002180aeb2dfc9ec4f606cc` |

评审指出受限外部 here-document 的拒绝发生在实际打开重定向之后。现在先完成
命令类型判断，再执行允许的 here-document 重定向。新增的两个入口回归均在真实
工作盘预置文件，尝试向该文件重定向，然后离线核对原字节。
从 `21f16cc5` 重建得到系统 `c244c7e24082e7ef`。QEMU 的 26 项检查和
files/FatFs 复验通过。ISO 为
`dcc81ddbc5c41d8d9c0712a67a84f90b18e039267c144c9b273e9558ba99aa40`，
glibc SDK manifest 为 `08f666ae4cc0f31d4fe417dcccc4283476120fed700002ffa133819877fb2fce`，
保留原文件的客体回执为 `f469eb34ffa6cc008fa31d1a21c1458daf6f96a88b1c7071005e45f559a0ae05`。

复核上游 `evalcommand` 后，将类别预检直接放在原有重定向点。允许的内建命令
仍在命令前置赋值之前展开 here-document。双入口脚本核对正文读到外部变量值，
临时赋值在内建命令结束后还原；同时重跑拒绝外部命令及其原文件字节检查。
从 `7f0bf0a6f5c31a46bc5a8a70e0b774fb08b8c0d9` 重建，两种入口合计 26 项通过，
files 宿主与真实 FatFs 检查通过。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `ec8b136ece22fa2e` 清单 | `dbef45fbb4ef3a4179086e5f78246b74afa53a8de5c5cd96842b74021d6be27c` |
| 系统 ISO | `1a275e8217db085167f5a7b5cf61b51855fad807a19b88c88b58515a9b6abbf9` |
| glibc C SDK 清单 | `c11710d5c435acf7842c1619ac136aae2642d14083800f53478bc2902c503a3f` |
| QEMU 回执 | `680c32a19a98e250c9a3c2ebd8aabd5dbb7743ed01cb3d6c815a3e9c6f7551ff` |
