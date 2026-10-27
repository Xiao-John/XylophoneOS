# libc与运行库适配

2026-10-27。当前采用newlib4.6.0.20260123、x86_64-elf静态链接；具体产物/配置/哈希以
对应SDK manifest为准，不把初版库大小或旧build/sdk当作所有后续SDK的身份。

## 当前实现

- CRT正常初始化/退出、heap、stdio、errno、文件/目录与受限posix_spawn；C++运行库、
  构造/析构、异常/RTTI、静态TLS和线程接入有各自gate，见[E08](e08.md)、[线程实现](implementation/threads.md)。
- SSE/x87按任务/线程保存，newlib/应用可使用所需ABI；内核仍遵循受限C++与寄存器约束。
- 普通SDK与线程SDK分开，后者使用newlib重入状态、锁/TSS/TLS和线程安全适配；不能用
  freestanding默认single线程模型替代真实pthread，也不覆盖旧冻结SDK。
- 文件描述符映射到files对象引用；共享打开描述、dup/CLOEXEC、32FD exec转交与匿名文件
  见[SDK](e04_loader_sdk.md)、[Shell](implementation/shell.md)。当前FD不代表完整POSIX。
- getentropy→sys63真实RDRAND接口；墙钟/gettimeofday→sys64，单调时间/睡眠走线程等待
  机制。输出大小、errno、不支持/硬件失败按各自契约；不以uptime或固定种子补安全接口。
- truncate/ftruncate接files op25；stat仍有合成属性。权限、链接、完整时间元数据、locale、
  signals、socket、通用就绪等待与mmap族未取得完整资格，缺项不能永远成功。

## 构建与使用

普通构建scripts/user_build.py导出头/CRT/libxos/libxos_loader/newlib/user.ld及许可，
scripts/build_threading_sdk.py另建线程/可选C++ SDK。第三方应用使用冻结SDK/profile，
见[快速开始](friend_user_program_quickstart.md)；不默认修改系统程序清单来安装软件。

适配集中于src/user/libc/newlib_syscalls.cpp、src/user/threading/与对应SDK/架构CRT。
新增接口同步公共定义、普通/线程生成器和真实消费者；pthread直接错误号与errno型接口
分别处理，不把同一个负内核返回无差别传播。

## 验收与许可

初版printf/malloc/string/exit和FXSAVE检查见[E01–E07](history/e01_e07.md)；原生C/C++、
线程、CPython与SDK身份绑定各自保留冻结证据。当前程序可运行不等于newlib全部接口合规。
newlib包含多来源许可；声明/组件清单见[许可管理](licensing.md)。材料检查与预构建库逐成员
归属审计分开，后者未完成的部分继续明确保留，不以libc文件名推定单一LGPL授权。
