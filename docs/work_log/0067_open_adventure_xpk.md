# 0067：Open Adventure XPK 构建和定向验证

2026-10-27。打包源码提交 `ff264f7`，此前输入/编辑工作已在另一工作区提交 `4003511`。
在独立工作区构建 1.12，生成 `games.open_adventure` revision 0，未发布。

## 构建

- 原生 XOS 客体执行 `python3 make_dungeon.py` 和 `src/ports/adventure/build.sh`；
  使用专用 FAT 盘，编译/链接所用 sysroot 文件来自已登记 B2 SDK，必要的路径按
  `build/open_adventure_package/build_driver.py` 映射。回执带生成物和端口摘要；
  二进制 SHA256 `21d3af297771e2be301caf0e5b9acde2923221e980f4a065ad2580518be3c9ae`。
- QEMU 11.1.2、TCG、单核 512MiB；系统 `build/input_edit_final/xos.img` SHA256
  `4f6e91523531fd1070694063ccbaccfa5b884a806a9aa99e16db43e1bd60c2f1`；
  Seed manifest SHA256 `327e2cb0f548dfb721b9ca968c2d3ec84f01e7633b0b3e9d5207bf3c7b5ea448`；
  SDK tree `e0fa2330a1c38c162f40857609ef88f97673d66e080069018ac26b85d4a5f110`。
- `scripts/record_open_adventure_build.py` 和 `scripts/package_open_adventure.py` 生成
  `build/open_adventure_package/open_adventure.xpk`，SHA256
  `5d31fadbdd89e998ec14d76f0fb2806df00dcfd4c5dd796eb307732876c489ec`，36 个文件，
  profile `xos-x86_64-static-single-b2-v1`。回执中的编译环境是操作者声明；不能把回执
  本身当成独立认证。日志、生成文件、ELF 与临时驱动保留同一 build 子目录。

## 实测

- 宿主 `xypm.py verify`：完整性和 profile 检查通过；在 512MiB 专用 FAT 盘离线安装
  导出候选，通过 `verify-installed` 逐项校验 36 文件。
- 从安装盘在 XOS 输入 `advent`，检查中文欢迎与初始地点，执行 `no`、`look`、`quit`、
  `yes`，正常退出 0 返回 Xshell；原始输出 `build/open_adventure_package/guest_run.log`。
- 宿主离线卸载产生新候选盘，`xypm list` 为空；不涉及个人数据的覆盖或删除。

## 限制

本轮没有客体 xypm 写安装（该能力仍未实现）、存档/恢复、全剧情、中文完整翻译、
断电/损坏注入或长期压力验收。磁盘事务是宿主离线候选方式，包结构验证不是签名或
信任证明。SDK 许可材料随包提供；静态运行库逐成员审计和公开发行义务未完成。
