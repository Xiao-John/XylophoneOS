# VM0 受限验收回执

2026-11-09；系统 build `e68f6403d72f1f58`，输入与产物摘要见
`system_manifest.json.gz`。QEMU单CPU、512 MiB，专用测试盘；dash 及匹配SDK输入见
`dash_manifest.json`。源码中 `memory_self_check` 在guest启动时验证页引用、跨旧窗口
复制、逻辑写权限以及四个分配失败点的资源精确回收；通过记录位于串口日志。

- E04进程13项、E05文件8项通过；`iso_regression_wrapper.py` 将测试专用目录的旧
  `xos.img`引用适配为本次构建ISO，原始系统manifest保存在本目录，适配manifest仅在
  build中生成。`process_report.json`、`file_report.json`及串口保存原始结果。
- dash C2 29项通过，包括真实fork ENOMEM回滚、继承、权限、重复回收和子shell。
  `dash_c2_report.json`及串口提供细节；不包括线程libc fork探针、SMP或长期压力。
- 线程集成中 `thread_core`、`thread_last`、`thread_arbitration`、`spawn_private_ordered_actions`、
  `B2_order_dup_append_input_builtin_restore`、`thread_model_nested_Escape`六项使用
  此组合通过。原`thread_merge_report.json`第七项`ISO_sys53_dash_payload`调用脚本中
  写死的其他构建镜像，不计入本次资格；保留原报告不改写。
- 初次QEMU调用因受限环境不允许本地socket失败；经授权后在同一云环境重试通过。
  原始旧回归脚本直接要求已移除的`xos.img`，失败记录保留。未修改旧冻结报告。

VM0不提供匿名reserve/commit、COW、真实多线程fork或SMP。逻辑写权限当前存于arch
页表软件标记，相关逻辑接口供内核调用，尚无VMA；未来隐藏提交页必须由VM1–3另行处理。
