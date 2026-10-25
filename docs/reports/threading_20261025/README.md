# 0037 冻结验收材料

源码基线 9c896df；最终系统 build b33da3d9929ace75。
35 组线程专项 + 37 项受影响旧回归 + 6 组原生 GCC/G++ 客体检查通过，共 78 组。
另有 SDK 产物/源码 SHA 核对、AArch64 通用代码编译及 7 份许可证材料检查。

qualification.json 的 reports.sha256 对应本目录公开副本；original_local_sha256
对应 build/ 原始日志。公开副本仅将本机绝对路径改为 <repo>/<home>，原始字节 SHA
和 SDK 冻结输入保留于 sdk_receipt.json；产物哈希/测试结论未改写。
失败过程保留在 threading_final_suite_attempt*.log，成功统一日志为
threading_final_suite.log，原生编译器日志为 threading_native_attempt1.log。

SMP、完整 POSIX 合规、T3-PY/T3-QT、长时间/随机压力、第二 ISA 运行及新二进制
公开发行不由本次结果证明。GNU/newlib 逐成员许可追溯仍未完成。
