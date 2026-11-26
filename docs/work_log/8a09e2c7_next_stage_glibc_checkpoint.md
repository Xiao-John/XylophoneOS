# 8a09e2c7 · glibc 与产品整合检查点

2026-11-26 · 从主线 `db8e15dd` 的归档在空目录构建系统
`1216ff833a45226f`，用项目锁定的 QEMU 11.1.2 完成 `make smoke`。
启动、内核、任务、进程、文件、持久化、磁盘满、libc、E08 存储及运行时共
79 项通过。许可审计确认 10 项材料。重跑：

```sh
git archive db8e15ddbf1c1f82ec7551bf4f67534bee6fc63d | tar -xf - -C "$EMPTY_BUILD_SOURCE"
make -C "$EMPTY_BUILD_SOURCE" smoke
```

使用现有源锁固定的 lwIP 输入。QEMU 11.1.3 的先期 Linux 尝试通过引导门，
随后被内核验收的版本锁拒绝。该次尝试保留为版本不匹配。以上通过记录来自
实际使用 11.1.2 的完整重跑。

| 工件 | SHA-256 |
| --- | --- |
| 系统 manifest | `17492b3c290b182f79493d745bd3181ef432f03969b2e112fa7233bbf82bda98` |
| 正常 ISO | `5a011f534499dc0b9cbb7f9b41671706047ba4071c133aa82bf54af155c9357d` |
| `make smoke` 记录 | `291c4400009f6ac733a014d84135d40f96d1e4cdf380ce188e8463e3219c5c5c` |

## 模块顺序与剩余资格

- glibc 正常进程和 dash 外部 ELF 已经合入。管道与重定向分别推进，日用工具候选
  明确依赖路径变更及后续描述符传递。SDK 默认切换仍需所有入选软件、回退和新旧 ABI
  的组合验收。 [进程 #193](https://github.com/Xiao-John/XylophoneOS/pull/193) · [dash #197](https://github.com/Xiao-John/XylophoneOS/pull/197) · [管道 #206](https://github.com/Xiao-John/XylophoneOS/pull/206) · [路径 #208](https://github.com/Xiao-John/XylophoneOS/pull/208) · [日用工具 #209](https://github.com/Xiao-John/XylophoneOS/pull/209)
- C/C++ 应用的 XPK 宿主候选盘生命周期和客体执行已通过。真实 glibc xypm
  在同一普通系统通过权限、事务、重启和用户文件保留的 8 项测试，逐步故障注入、
  断电和包管理器自升级单独验收。 [应用 #205](https://github.com/Xiao-John/XylophoneOS/pull/205)
- Qt Quick 已验证软件场景，独立应用真实构建、呈现、退出并恢复资源。
  Mobius 的 glibc 桌面和会话已进行真实图形验收，会话加载测得约 193 秒。
  目标 XPK 与启动延迟继续隔离验收。 [Qt Quick #198](https://github.com/Xiao-John/XylophoneOS/pull/198) · [独立应用 #203](https://github.com/Xiao-John/XylophoneOS/pull/203) · [Mobius #210](https://github.com/Xiao-John/XylophoneOS/pull/210)
- Pumpkin 存储适配器已合入。开发 headless 配置实际使用盘外代际记录，健康盘重启
  保留吊销，全盘恢复旧版本拒绝启动。生产授权、物理断电及正常系统组合仍须资格。
  [适配器 #204](https://github.com/Xiao-John/XylophoneOS/pull/204) · [三次启动 #207](https://github.com/Xiao-John/XylophoneOS/pull/207)
- ClarkE 已通过真实 pthread 和栈范围探针。继续锁定目标布局生成证据，之后验证
  单 mutator 解释器、WTF/JSC 链接和客体运行。WebCore、生产网络及浏览器发行留给
  对应 gate。 [线程基础 #202](https://github.com/Xiao-John/XylophoneOS/pull/202)
