# P1-F ClarkE 全页集成恢复记录（进行中）

## 范围与交付门

本线实现 `docs/plans/p0_completion.md` 的 P1-F：真实 WebCore 页面解析、DOM/CSS
布局与软件绘制、Qt 视口、独立 renderer/network 进程，以及导航、取消、故障后的
资源回收。静态归档、tokenizer、liteHTML 或伪造平台成功值均不构成此项验收。
恢复基线为 `6332527ab64e92371266363f41f3247717a3cac8`，包含 P1-B 进程树预算与
P1-E 主线变更。本记录的进行中快照用于保存可审查源码，不代表 P1-F 完成。

## 环境中断与证据边界

2026-11-28 执行环境断开后恢复到了较早磁盘快照。本线工作树、未发布的 SDK、
依赖前缀、WebCore 对象及运行日志均未出现在恢复的磁盘中。恢复前对话中记载过
构建进度和测试结果，但其原始产物、日志与 manifest 不在当前证据集中；不能将
这些摘要当作本次可复核资格。本线从远程主线重建，逐步保存明确标注为进行中的
远程源码检查点，再重新生成构建与客体证据。

## 本快照已恢复的实现

- `src/ports/webkit/target_inputs.py` 验证依赖的完整 artifact 清单、SDK tree、
  头文件覆盖、规范路径与别名目标；仅允许 ICU 已独立记录的前缀内元数据别名。
- ICU 构建记录全部已安装文件与头文件，记录实际 SDK/profile 摘要。
- 字体构建可显式消费同一 SDK 重建的 ICU；旧 ICU archive 入口仍要求旧版完整
  SDK 绑定，不能悄悄把历史资格转到新 SDK。
- libxml2、Skia、Fontconfig 的重建链绑定当前完整 SDK 与实际依赖清单，不再
  把历史报告的哈希作为唯一可构建前缀。
- SQLite 构建使用既有 Files VFS、真实 pthread mutex、单 renderer 进程的
  exclusive rollback journal 范围，关闭 WAL 与动态扩展。未宣称跨进程数据库锁。
- 源码下载器只读取既有锁中的来源与摘要，不升级依赖；签名验证仍由各端口准备
  工具执行，下载完成不等于构建或客体合格。

## 已重新执行的检查

恢复后的普通宿主 Python 执行：

```sh
python3 tests/test_webkit_target_inputs.py
python3 -m py_compile src/ports/webkit/target_inputs.py \
  src/ports/webkit/page/build_sqlite.py src/ports/webkit/icu/build_target.py \
  src/ports/webkit/fonts/build_target.py src/ports/webkit/libxml2/build_target.py \
  src/ports/webkit/fontconfig/build_target.py src/ports/webkit/raster/build_target.py
```

8 个依赖绑定负向/正向用例通过；Python 语法检查通过。该结果只验证宿主配方的
输入边界，不代表 XOS SDK、WebCore、Qt 或网络客体通过。

## 当前未验项与继续顺序

1. 在已发布 preview-3 Linux SDK 中重新生成唯一静态 glibc C/C++ SDK，并交由
   P1-D 只读消费；动态 GNU runtime/bootstrap 由 P1-D 在 C 接口冻结后另建。
2. 重建全部锁定依赖和真实 WebCore full-page ELF，补齐实际链接所需平台实现。
3. 完成固定 ELF 安装绑定、Xsh prestart 预算与 net2 撤销、子进程自有 IPC pair、
   Qt backing-store flush ACK 与明确的 navigation/cancel/failure 清理。
4. 运行 DOM/CSS 几何与像素、真实 Qt scanout、HTTP/受控 HTTPS、原始 net2 拒绝、
   越权 release、超过 16 次导航、renderer fault 与实际 start/abort 故障客体。
5. 保存平铺证据 manifest、实际暂存索引公开路径检查；完成后再提交可合并 PR。

全部全页、Qt 和生命周期客体验收在此快照中均为 **未运行**。
