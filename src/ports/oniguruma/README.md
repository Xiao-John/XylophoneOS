# oniguruma（上游 Oniguruma 6.9.10）

把 Oniguruma 正则库作为纯客体包交付：静态库 `libonig.a`、三个公共头文件与一个
正则探针。不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

## 状态

`guest_verified`（2026-11-12）。上游零补丁；**xsh 与 dash 两条路径都实测**。
证据见
[docs/reports/oniguruma_6_9_10_20261112](../../../docs/reports/oniguruma_6_9_10_20261112/README.md)。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，用 CMake 交叉构建（Debian 的 orig 包不带 `configure`）：

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/libonig_6.9.10.orig.tar.gz
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/oniguruma/build.py
```

产出 `$XOS_OUT/thirdparty.oniguruma-6.9.10.xpk` 与 `$XOS_OUT/build_receipt.json`。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_onig.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  "$XOS_OUT/thirdparty.oniguruma-6.9.10.xpk"
```

已验证的包哈希：`fcfda1a8a46fe9d1efcca3b006eb1f9043386ac19f5847ddb9bb282aaa72e8f5`

库没有命令行入口；验收方式是编译包内探针 `samples/regex.c` 并运行：

```sh
x86_64-elf-gcc -O2 ... -I <tree>/usr/share/oniguruma/include \
  src/ports/oniguruma/samples/regex.c <tree>/usr/lib/libonig.a ... -o regex
```

客体（xsh 与 dash 均实测）：

```text
exec-file /tests/regex
    start=2 end=7 groups=2
    ONIG_OK
```

`jq` 的正则族（`test`/`match`/`capture`/`scan`/`sub`/`gsub`）已可通过 jq 端口
静态链接本库直接使用，见 [jq 端口](../jq/README.md)。

## 已知限制

- 只验证 UTF-8 编码与默认语法；未覆盖其它编码/语法/posix 接口。
- 未跑上游 `tests/`。
- 头文件放在 `/usr/share/oniguruma/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、`/usr/share`）。
- 源码哈希来自 Debian 镜像的 `orig.tar.gz`，未与 GitHub release 附件二次比对。
