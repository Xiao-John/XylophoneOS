# 0068：UTF-8 文件名

2026-10-27。实现并作定向客体验证，源码提交 `7ca7ede`、`0f6b7c8`、`09fd31a`。范围：FatFs UTF-8 API、文件服务
路径及目录枚举、SDK 和 newlib 路径、长短名对象身份保护，以及独立测试。路径长度仍为
最多 255 字节；不做 Unicode 规范化，大小写只折叠 ASCII，包格式仍限 ASCII 路径。
不新增 ABI；已有客户端为静态链接，须重新构建以使用更新的 SDK。

最终 build `113f64c25dc336e7`，镜像 SHA256
`f2efeb7bf5ca116afc98cb845dba6f542fc1c43ffa7e3bd81d6d04bf9573e7a6`。
`python3 tests/utf8_filename_smoke.py --image build/utf8_filenames_qualified/xos.img --sdk
build/utf8_filenames_qualified/sdk --report build/utf8_filenames_qualified/utf8_filename_report.json`
通过：中文目录/文件创建、枚举、读取、改名、sync、重启和删除；新 SDK 构建的独立程序
验证 open/readdir/rename/read/unlink 及非法字节拒绝。`python3 tests/file_recovery_guest.py
--system build/utf8_filenames_qualified` 5 项通过；`python3 tests/xsh_ui_smoke.py --system-dir
build/utf8_filenames_qualified --output-dir build/utf8_filenames_qualified/xsh_ui` 11 项通过。
Xshell 测试使用从原工作区复制的既有 dash；许可材料检查 7 项通过，逐成员审计未完成。
旧候选 build `936b196e7884254a` 的文档/ABI检查通过；最终代码只改文件服务错误分支。

仍需补充较长多字节文件名、非 BMP、目录枚举溢出、长短名别名并发、满盘/故障和中文路径
恢复日志等边界。FatFs 遇到外部过长 LFN 可能显示短别名；OEM 转换仅支持 ASCII，非 ASCII
大小写按原码点比较，不提供 Unicode 规范化或完整 FAT Unicode 大小写折叠。xypm 包文件
路径仍是 ASCII；不能据此宣称完整 UTF-8 文件生态。测试只用独立盘，不修改其他工作区。
