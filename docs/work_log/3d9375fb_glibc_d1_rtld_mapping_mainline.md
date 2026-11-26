# 3d9375fb · GNU rtld 原生依赖映射主线复验

将依赖映射变更移植到 `e783fce2` 主线，并核查 #260 的启动栈修订。真实 GNU
共享装载器对象复用 XOS 加载端的原生段映射规则。路径由已认证的只读文件句柄
提供，复制数据时保留段边界，回收时对大型保留区分批提交撤销请求。

在断网 Linux ARM64 交叉构建环境中，从锁定且上游签名验证通过的 GNU glibc
2.44 重建静态 C SDK 和目标 rtld 对象。普通系统 `fb8a9457764f8fba` 与该
SDK 的 profile 一并进入客体。QEMU 11.1.3 经 dash 执行原生工具，映射并调用
6 页和 8196 页两个实际依赖，核对读、执行和写段，以及保留的洞。退出后
129696 空闲页、3 项任务和 1 条完成记录均回到原值。真实静态 glibc 继续从
继承文件读出 `EFGH`，请求序号由 69 到 71。
[客体回执](../reports/glibc_d1_rtld_mapping_mainline_20261126/report.json)

完整 `ld.so` 的原生启动守卫继续启用。该客体执行了实际共享装载器编译出的
映射对象，真实入口闭包、早期分配和最终 TLS 启动按 D1 后续门验收。

```sh
python3 tests/glibc_d1_rtld_mapping_guest.py --system "$SYSTEM" \
  --sdk-build "$GLIBC_SDK" --profile "$PROFILE" --dash "$DASH" \
  --dash-receipt "$DASH_RECEIPT" --rtld-proof "$RTLD_PROOF" --output "$OUTPUT"
```
