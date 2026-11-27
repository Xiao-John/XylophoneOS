# glibc D2-C · 固定闭包的公开加载拒绝

[D0 固定闭包合同](../contracts/dynamic_linking_d0.md#8-d1d4-验收与交付边界)
要求当前公开 `dlopen`、`dlmopen`、`dlclose` 用实际错误拒绝运行期装卸。
现有 [原生 GNU D1](glibc_d1_linked_interpreter.md) 与
[固定闭包 GNU C++](glibc_d2_shared_cxx_fixed_closure.md) 已覆盖初始 TLS、
启动期依赖、构造与析构。本次核对启动完成后的公开入口。

使用 [Net2 GNU 共享重链](61202e5f_glibc_net2_tcp.md) 的真实 GNU `ld.so`、
`libc.so.0.1`、C SDK 与普通系统 `6ee274714e525f50`。该验收源码
`61202e5f` 到当前专项基线 `89de1a04` 的 glibc 端口和原生 loader
源码逐文件相同。客体仍使用原镜像，源文件按原系统清单核验。

原版客体观察到 `dlopen(NULL)`、`dlopen("libc.so.0.1", RTLD_NOW)`、
`dlmopen(LM_ID_BASE, "libc.so.0.1", RTLD_NOW)` 均成功返回公开 handle，
`dlclose` 均返回 0。一个不存在的库名触发既有的固定闭包拒绝。前三个成功
表明已有映射仍可通过公开入口获得 handle。

修复把三条公开操作的拒绝放在 XOS 共享 libc 的入口，复用 GNU `_dlerror_run`
传递 `ENOTSUP`。只重编 `dlopen.os`、`dlmopen.os`、`dlclose.os`，在
私有临时盘重链接共享 libc。PIC 归档逐成员比较只发现这三处变更。原归档对照
独立重链接复现原 libc 摘要。两次独立临时目录重链得到同一修复 ELF
`87831702…106a`。解释器、版本化导出集合和 `DT_NEEDED` 保持原有行为。

| 真实 QEMU 用例 | 观察 |
| --- | --- |
| 原版公开加载 | 3 个既有映射 handle 成功打开和关闭，未存在名称拒绝 |
| 修复后公开加载 | 4 个调用均返回空指针和 `ENOTSUP`，第二次 `dlerror` 读到空 |
| 原 D1 C 回归 | 构造、环境、auxv、文件读取、errno 通过，退出 0 |
| 同一合法 libc 文件缺 startup pin | GNU 装载拒绝，退出 127 |

四组资源均恢复到 `129696 / 3 / 1`。修复后公开入口无法获得合法 handle。
`dlclose` 的修复以最终 ELF 反汇编为证，入口经相同的 `_dlerror_run`
并返回 -1。静态构件、`dlsym` 与 `dlvsym` 的契约以及共享工作线程分别
沿用各自当前验收范围。
[绑定、四组客体和原始串口](../reports/glibc_d2_runtime_load_policy_20261127/manifest.json)

## 复验

用原 Linux 交叉构建环境。将 Net2 确切构建树的宿主目录只读挂到 `/work`，
保持已配置绝对路径与原始日志一致。将本专项源码置于另一目录，`OUT`
指向新证据目录。使用已配置的实际 GNU 构建目录及绑定的交叉工具。

```sh
export PYTHONPATH="$PWD/scripts:$PWD/tests"
SHARED=/work/build/glibc-net2/shared
python3 -B tests/fixtures/glibc_d1/replay_dlfcn_policy.py \
  --shared-build "$SHARED" \
  --pic-log-sha256 577291c85b7b14c9fd747720ead4a6fbed985b0dc2d1c79f5ab2e7f858edfddb \
  --link-log-sha256 1c8c9b2d7622c17e64118ff7472d5c98bb12d33ef5458d6199c3654c580c1a66 \
  --libc-sha256 50452962afeeadcd6b3bcecd3571cc6b07f29c80e30426715d8134a86fc9d8d0 \
  --output "$OUT/rebuilt"

ROOT=/work/build/glibc-net2
for fixture in runtime-load-policy c unlisted; do
  python3 -B tests/glibc_d1_linked_interpreter_guest.py \
    --system "$ROOT/system-net" --system-source /work --sdk-build "$ROOT/sdk-v2" \
    --gnu-build "$SHARED/gnu" --dash "$SHARED/dash.elf" --dash-receipt "$SHARED/dash.json" \
    --libc-image "$OUT/rebuilt/libc.so" --case "$fixture" --output "$OUT/$fixture"
done
python3 -B tests/glibc_d1_linked_interpreter_guest.py \
  --system "$ROOT/system-net" --system-source /work --sdk-build "$ROOT/sdk-v2" \
  --gnu-build "$SHARED/gnu" --dash "$SHARED/dash.elf" --dash-receipt "$SHARED/dash.json" \
  --case runtime-load-observe --output "$OUT/untouched"
```
