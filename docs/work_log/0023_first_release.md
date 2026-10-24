# 0023：10.24 首个正式发行

用户授权发布 XylophoneOS Revival version 0.0.1-1024，GitHub 标签 v0.0.1-1024。
主端负责发行包、版本/说明、Git 提交/标签/Release；Luna 分别负责独立启动器/说明
和 GNU 对应源码材料；压力从端继续其独立测试，没有构建/清理其共享产物。

## 冻结与验证

没有重新构建内核。复制已验收 build 2c3876e640840ff5 的镜像和 SDK；xos.img SHA256
1c2cfa90d65b9a9585ac3d5cef32c8376b1806e65f7502321912b2e15b54454c。
发行版本与内核内部 build ID 分开记录；标签源码另增加发行脚本和文档，不将原构建
source digest 冒认为标签完整树的摘要。

scripts/package_release.py 在独立 build/releases/0.0.1-1024 创建 2 GiB FAT32
盘，按组合清单逐项校验并安装 174 个 Seed 文件及 1036 个 sysroot 文件，附 C/C++
示例。SDK 增加目标 C++ 库、头和独立 compile.py；启动器不依赖仓库构建。
scripts/package_release_sources.py 收集上游原包、实际修改覆盖层、配置、补丁、许可
与可取得的构建记录，详见 releases/source_materials.md。

实际执行 python3 scripts/package_release.py；发行 SDK 的 compile.py 分别编译
examples/hello.c 和 hello.cpp 成功。python3 scripts/release_smoke.py 使用发行工作盘
的独立 APFS 副本，在冻结镜像中通过 packaged_native_c、packaged_sdk_c、
packaged_native_cpp、packaged_sdk_cpp 四项，并 sync 成功。日志 build/release_package_serial.log，
报告 build/releases/0.0.1-1024/package_smoke_report.json。发行原始工作盘未被运行时修改。

本组没有重跑旧回归或压力矩阵；压力结论由从端报告负责。正式发布元数据和 SHA-256
清单记录各附件，GitHub 发布地址：
https://github.com/Xiao-John/XylophoneOS/releases/tag/v0.0.1-1024 。

已于2026-10-24 23:53:21 CST公开，Release ID 422824554，draft=false、prerelease=false。
8项附件的远端大小和SHA-256均与本地匹配，公开API再次读取成功，匿名下载CHECKSUMS.sha256与本地逐字节一致。源码提交
0e541badf27a23e2928881279cff5f165de8b4c9，标签不移动。对应源码主包另配
gxx_lrealpath_v5/open_capacity_fix派生修复补遗；校验清单覆盖两份源码材料。
公开发行回执存releases/release_0_0_1_1024.json。活跃压力侧的e08_post5_p1.py、
e08_post5_plan/report和e08_gcc_stress_plan留在原工作区，未误收进本次源码标签。

下一步由压力侧继续测试与汇报；后续测试发现的问题单独登记，
不要重写本次 frozen image 或移动已公开标签。
