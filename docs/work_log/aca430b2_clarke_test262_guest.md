# aca430b2 · ClarkE JavaScriptCore 的 Test262 子集

固定 TC39 Test262 修订 `4db99ac4dc8924279ae07ed3246385924e878519`。逐一核对
所选文件在该修订的 Git blob，并登记 SHA-256。选取八个同步正向脚本，覆盖
Array、Map、Set、JSON、TypedArray、可选链、类和生成器语法以及迭代。
[锁定的上游修订](https://github.com/tc39/test262/tree/4db99ac4dc8924279ae07ed3246385924e878519) ·
[文件锁](../../src/ports/webkit/test262_lock.json)

按上游默认语义，给每项分别运行普通和严格模式。每次由 xsh 启动新
JavaScriptCore 进程，先加载上游默认与显式声明的 harness，再单独解析测试脚本。
模式前缀只作用于测试脚本。客体必须实际执行结束标记并退出 0，每次核对空闲页、
任务和完成记录。
[上游执行规则](https://github.com/tc39/test262/blob/4db99ac4dc8924279ae07ed3246385924e878519/INTERPRETING.md)

从 `492f37ea` 与本实施提交构建普通镜像 `989535c8fd694853`。锁定的 QEMU 11.1.2
通过 16 次执行，资源均返回 `129696 / 3 / 1`。镜像和 JavaScriptCore ELF 复制到
私有测试输入并按各自回执核验，Test262 输入使用已检查的同一批字节。
[客体回执与串口](../reports/clarke_test262_guest_20261126/manifest.json)

本回执的分母是已锁定的 16 次同步脚本执行。模块、异步、其他功能和完整套件仍需
扩展验收。

```sh
python3 tests/jsc_test262_guest.py --suite "$TEST262_CHECKOUT" --system "$XOS_SYSTEM" \
  --payload "$JSC_ELF" --engine-binding "$JSC_BUILD_BINDING" --report "$OUTPUT" \
  --expected-resources 129696 3 1
```
