# 0035：包管理P0独立开发与打包闭环

2026-10-25。用户已把多线程实现交朋友、等待PR，本线优先包管理。主agent只占
scripts/xos_app.py、xpkg.py、xpkg_format.py、config/package/、tests/package_p0_*
及对应文档/状态，不改线程、ABI、内核、libc或Open Adventure/CPython/UTF-8源码。
没有派子agent，没有给其他线程发消息；尚未提交/推送本批或别人的未完成改动。

## 已实现

- xos_app init/build/check/pack：仓库外独立C/C++项目，普通main，显式冻结SDK，
  固定静态构建；源码/资源/SDK/构建器/产物摘要绑定，失配拒绝旧产物打包。构建
  使用临时输出，失败不把旧ELF写成新结果；输出包独占创建，不覆盖已有包。
- 版本化app_v1/xpk_v1 schema、保守静态单线程profile。当前只登记完整发行SDK，
  1046文件tree摘要e78726755d11d19feabcb7c36faebf6ed9a4e663f85f6beb081ffabae105a874。
  不接受任意build/sdk、未知新线程ABI或同版本混库；profile不是签名或一般ABI证明。
- xpkg宿主pack/inspect/verify；ustar普通文件子集，目录隐含。严格JSON/UTF-8、
  成员/大小/路径/重复/大小写/父文件冲突、归档header/终止/哈希和executable的受限
  ELF布局检查，拒绝链接/PAX/显式目录/短名别名~等。流式哈希与临时文件限制内存。
  不带profile只验格式/完整性，带profile再验声明feature，不执行任何payload。
- 模板包带示例源码、自选应用许可、真实SDK声明和构建回执；第三方条款保持原样，
  材料携带不假称逐成员许可审计。无新外部依赖，自研新文件Apache-2.0。

## 实际验证

宿主Python3.12.15，GCC/G++16.2.0，QEMU11.1.2。输入SDK为
build/releases/0.0.1-1024/xylophoneos_revival_0.0.1-1024_sdk；不修改它。

```sh
python3 tests/package_p0_cases.py
python3 tests/package_p0_guest.py
```

宿主16组通过：在宿主临时目录（位于XOS仓库外）创建真实C/C++项目并构建，检查
声明/源码变化拒绝、错误SDK、重复打包摘要一致、畸形JSON/归档/路径/链接/损坏/
缺项/覆盖/ELF错误等。旧E08/PY0/UTF-8/压力未重跑。

专用新盘的2项客体执行通过：两个包各28文件，先完整校验再由已有FatFs文件桥
传入新盘，普通exec-file启动，C/C++各正常退出0；每项资源恢复[130342,2,0]。
冻结系统build2c3876e640840ff5，镜像SHA256
1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
没有重建/替换系统镜像，且没有操作日常盘/发行附件。桥接工具摘要见guest_report。

最终产物（build/package_p0/）：

- c/app.elf SHA256 77f2b3a4adb399adcba5f10ef1150c2c0ce6cf6852036b7b9d4f5cc7ed0ba163
- c/app.xpk SHA256 f0cde6cc140b6c7e6a7295f5b24c6d6b15b6c4b1fe8dd27b9892eb75bbf9ecf9
- cpp/app.elf SHA256 f67dff5ad9fc52202f9492ef3559bb618cf92f54f2085ef1bffab93a887ffe87
- cpp/app.xpk SHA256 00b674d87e5a218c31fc7d994e423e3379ec919b806729d220f2d3ade7d31f4c
- final_receipt.json SHA256 2bd7763091d9a2831d2c0924b9376abb653e67161d906fd971f7b056d8d4d6e7

host_report.json、guest_report.json、guest_serial.log及最终源码哈希在同目录。
每次修改工具后只重跑本批受影响gate，早期包留在专用输出目录；上述是最终回执，
不把旧实验包摘要混为最终产物。

首次C++因C头放在C++包装头之前导致include_next找不到stdlib.h，已改为idirafter，
随后真实std::string编译/打包/客体通过。ELF检查对齐/堆保留区/TLS模板包含关系
按现有loader核对修正；工具中的预检不代替客体最终校验/授权。

## 文档、范围与下一步

主计划v0.9、包管理使用说明/格式、独立项目快速开始、线程实施分工、索引/决策/
state同步。用户指定的优先级覆盖0032的“本线先线程”建议；线程由朋友PR实现，
主端负责接收整合，当前不预占其源文件。

P0受限完成；P1候选盘安装/数据库、升级/移除/依赖执行、P2客体xpkg维护事务、
P3仓库/签名均未实现。当前客体gate是已有文件桥传输，不是包安装器验收。P0
解析器禁止~只是拒绝显式别名，P1仍须检查真实盘的LFN/短名与既有文件归属。
CLI尚不具备通用外部构建系统适配或线程SDK支持；高级端口可用显式stage/manifest。
下一组先P1无依赖新装：全会话锁、独立候选镜像、归属数据库、失败源盘不变；再
升级/移除/依赖，不能直接在日常盘试。localpilot未读/未改。本组无剩余编辑占用。
