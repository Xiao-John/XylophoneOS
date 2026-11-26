# 10da254a · glibc 工作目录与路径权限查询

`getcwd` 和 `chdir` 通过现有受认证的 XOS files 会话读取和更新工作目录。当前目录
由服务保存，已有的启动继承与相对路径解析继续使用同一状态。`getcwd` 支持调用方缓冲
区和 glibc 的分配形式。路径解析和长度检查由当前服务处理，失败沿用文件服务的错误映射。

`access` 使用真实文件元数据验证存在性、读取及 FAT 写保护。虚拟 `/dev` 不可写，
`/dev/null` 可读写。目录搜索通过服务解析路径。普通文件的 `X_OK` 通过固定内容的
句柄进行定位读取，调用现有 XOS ELF 加载器的结构检查，并释放句柄。该检查覆盖 XOS
静态 ELF 文件格式。进程创建、描述符继承和资源配额仍由对应的启动操作判定。

本次使用现有的文件消息、状态、加载器检查和系统调用。FAT 采用既有的权限投影。
`faccessat`、POSIX 用户组权限和动态 ELF 属于后续工作。

## 验证入口

[静态 glibc 来宾门禁](../../tests/glibc_static_guest.py) 的 `cwd` 套件接受同一系统
生成的 newlib dash 回执、常规系统镜像和经过源码签名校验的 glibc C SDK。夹具先用
现行 newlib `chmod` 写入真实 FAT 只读标记，再用 xsh 和 dash 运行同一 glibc ELF。
dash 在启动前切入子目录，用于检查初始工作目录的真实继承。两条入口都检查退出码、
路径及权限错误、UTF-8 目录和资源恢复。

Linux arm64 宿主上重新构建静态 C SDK 和正常 BIOS 系统。glibc 源码为签名验证通过的
2.44 归档。新 SDK 的 `gnu/stubs.h` 无这三个接口的 stub 声明。

| 证据 | 结果 |
| --- | --- |
| 系统 `82059a22340cf7ad` | ISO `fd0e4c8f20708e692427a90c0d5e7002dd33f404270f201ba33a533bc415ea61` |
| C SDK manifest | `0186574ed569f6cd25919f9e905a3b28537d85b04c913e2453d4d483eeed4b21` |
| C 测试 ELF | `277cc592c3029b4da0a543febc5e85e843594f9ffe0233931ac7d805ca7789dc` |
| xsh 与现行 dash | 各两轮通过，退出 0，资源均恢复到 `[129700, 3, 1]` |
| 文件运行库回归 | 47 项宿主检查和 14 组真实 files 服务与 FatFs 集成检查通过 |
| 来宾报告 | `85e8fd96aed03c50ac5300a017885368b15fc10dba9dbd14b35928ccad7743cc` |
| QEMU 11.1.3 串口日志 | `390f1805d9ed50377f5f5f74050ca683462b24d7acd37095dc6aabd7ea4779e3` |
