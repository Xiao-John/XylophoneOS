# Qt主线：阶段与底座依赖

2026-10-28。QtBase 6.8.3 静态 QtCore 已在 XOS 客体完成受限 G01/G03 功能资格；
准确特性、预算采样、禁用能力及证据见 [0064](../work_log/0064_qt_e15_qualification.md)。
发行许可与绝对内存峰值未完成；QtGui/QPA 尚未实现，G04 另行验收。

## Widgets与QML/Quick分开

| 面 | Widgets | QML/Quick |
|---|---|---|
| 首个交付 | raster窗口→控件→小编辑器 | 无界面QML/QV4→Quick软件场景 |
| 公共依赖 | QtCore、事件分发、线程/时钟、文件、字体/输入、QtGui/QPA | 同一平台底座，另核JS/GC/导入/绑定和渲染调度 |
| 扩展 | 布局/选择/保存、错误恢复、多窗口等实际需要 | 动画/生命周期/内存、帧时与效果子集 |
| 阶段 | E15→E16→E17 | E15→E18，E16+E18→E19；不依赖Widgets完成 |

Qt是GUI主线，SDL只是复用窄平台服务的次选消费者，不作为Qt中间必经层。
首轮沿用CPU raster/Quick软件方向，不把GPU、JIT、动态链接、SMP或完整POSIX当作首窗前置。

## 当前缺口与分工

- QtCore事件分发：受限 posted event/计时/跨线程唤醒已有客体验证；wait_word和显示
  wait不自动等于通用poll/select。E16先核显示与跨线程组合等待，必要时提出通用机制。
- QtGui/QPA：接display_client的实际mode/stride、局部呈现、输入/焦点/退出。服务当前
  单surface；不直接调用BIOS/映射MMIO，不从旧G02报告推定任意窗口语义。
- 文件/路径：核短读写/错误/资源路径，当前ASCII路径与UTF-8内容分开；权限/链接/locale
  缺口按消费者提出，不假报全POSIX。
- 内存：核堆/大对象/对齐/峰值；VMA/mmap/mprotect尚未实施，首轮实际需要与可用回退分别验证。
- 运行库：验证所选Qt需要的C++构造/原子/TLS/线程退出与功能配置；不能使用内核禁用选项
  盲裁全部应用，也不能用旧C++探针代替Qt线程接入。
- 构建：先用同版本宿主moc/rcc/uic等生成器交叉构建；目标Qt应用运行、目标端构建应用、
  目标端重建Qt分别验收。QPA按固定Qt版本维护，不承诺跨版本兼容。

接口/文件所有权与ABI分配见[Qt协作契约](../contracts/qt_platform.md)、[ABI表](../contracts/abi_registry.md)。
验收按[GUI G01–G10](../acceptance.md)，Widgets与Quick分别记录预算、错误/回收与未支持项。
Qt/字体/图片组件按实际模块核许可与来源；静态分发的源码/补丁/重链接对象及配方、替换运行
说明在发行前单独核对，不把Qt整体改为XOS授权，也不以本计划代表许可审计完成。
