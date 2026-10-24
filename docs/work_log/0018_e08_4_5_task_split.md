# 0018：E08-4/5 主从分工与执行prompt

2026-10-24，主agent完成文档分工；未启动实现、未派发Luna或另一聊天。

用户要求加速E08-4/5，将任务分给当前主agent（可用Luna）与另一协作agent，
并确保当前agent主导。按改动所有权拆分，不将C阶段与C++阶段硬分给两人：
GCC自身先需要C++运行闭包，单按语言拆会重复构建并让两边同时改ABI。

主agent负责系统运行基底、权限/ABI、SDK与最终验收；Luna分别承担指定libc/探针
和新功能测试。另一agent独占GNU GCC构建/移植配置、依赖/许可材料及私有cache。
E08-5的源码/配置准备可并行，正式gate仍在E08-4之后，异常/RTTI/TLS基线不降级。

新增docs/prompts/e08_4_5_primary.md、e08_4_5_secondary.md和协调入口
 docs/e08_4_5_coordination.md；state和E08阶段计划增加链接。写明不可变SDK、
静态工具重链接、主agent独占build/、collect2等实际进程树权限和交付manifest要求。
后续压力测试仍由专人负责，只新增功能gate与实际bug定向回归。

验证：文档范围/依赖/文件占用静态核对，git diff --check通过。
未运行构建、客体测试、依赖下载或子代理；E08-4/5仍not_run。
无代码/许可依赖改变，localpilot未触碰，未提交/推送/读取凭据。
下一步：用户将协作者prompt交给另一agent，主agent执行自己的prompt并登记实际占用；
不将本次准备文档误认作已有人员启动或GCC功能完成。
