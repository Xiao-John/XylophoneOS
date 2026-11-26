# 5a828b33 · dash 原生 fork 后的 glibc C/C++ SDK

在干净的 #290 合入树 5a828b33 重建签名 glibc 2.44 C SDK。实际安装的
pthread_self 声明为 extern pthread_t pthread_self (void) __THROW，头文件摘要
为 e1222d3f1dfe88fb9e0db5512b6744bc2b964d34c196a6e23ecc3be9e4514f47。
C SDK 的分配器与 pthread 互斥加锁检查通过。SDK profile 校验宿主套件通过 45 项。

复用已验证过的 GNU GCC 16.2.0 XOS 配置方式，从签名归档重新编译 POSIX
libstdc++、libsupc++ 和目标 C++ 标头。GPG 同时核验主密钥指纹
13975A70E63C361C73AE69EF6EEB81F8981C74C7 与签名子密钥指纹
7F74F97C103468EE5D750B583AB00996FC26A641。封闭的 GCC 编译容器只读挂载本轮安装
的 glibc C sysroot。libgcc 的 DWARF2 展开、帧注册、SJLJ、C personality 和
emutls 五个对象也在同一 C sysroot 上重新构建。归档比对确认其余交叉编译器运行库
对象字节未变。组合归档必须保有对 pthread_once 和 pthread mutex 的强引用。

实际装配验证后以独立 profile xos-x86_64-glibc-stock-fork-v1 运行
package_glibc_sdk.py。它显式启用目录、线程、stdio transfer 和 C++。现存 profile
同名包数据继续绑定各自 SDK，应用应在切换后重新构建和打包。

## 重建入口

使用干净对应源码树与校验文件列出的交叉工具。运行 build_glibc_sdk.py 的
--archive 和 --output 入口取得目标 C SDK。将验签所用 GCC 源归档、签名和锁定
keyring 放进独立材料目录。容器 /work 挂载 C++ 编译目录，/work/sdk 只读挂载
这次 C SDK，material 中运行证据附带的两个原始编译脚本。证据中的 assemble.py
将两次编译结果与经验证 SDK 附带的已锁定本地 GCC 材料合并。用
create_xypm_profile.py create 生成本次 profile，用 package_glibc_sdk.py 装配部署目录。
证据中的 guest.py 使用正常启动的系统镜像、部署目录及同 SDK 生成的 dash 回执。

## 客体

普通镜像 2c1934f4bee40fb9 在 QEMU 11.1.3 实际启动。xsh 分别三次运行线程与
TLS 夹具和异常析构夹具。使用同一 SDK 重建的 glibc dash 三次运行两个 ELF 及
命令替换。9 项均退出 0，资源均恢复到 129709 页、3 个任务与 1 条完成记录。
两份 ELF 经 FAT 读回并绑定各自编译回执。新旧 SDK 和 profile 的交叉搭配均被
宿主工具拒绝。

## 配置恢复与证据

旧构建配方的编译器检测中缺少 fresh SDK 的终端静态归档，第一次 configure 退出 1。
保留原始配置日志，从已通过验签的源码展开目录重新配置时把该 SDK 的
libxos_terminal.a 加入链接组。最小 x86-64 ELF 链接和重建均通过。证据内第一个
编译脚本保留当时的配方，实际校正步骤由 reconfigure_cxx.sh 记录。两个配置和展开
阶段日志在构建目录各自保留。新旧 c++config.h 中有值的 _GLIBCXX_ 宏均相同，包含
POSIX gthreads、C++11 ABI 和 dual ABI。

本轮 SDK、profile、产物、源验证与客体见证由同一索引绑定。产品批量升级、正式默认
切换及 newlib 退役继续依各自的验收门。
[证据索引](../reports/glibc_stock_fork_sdk_20261126/manifest.json)
