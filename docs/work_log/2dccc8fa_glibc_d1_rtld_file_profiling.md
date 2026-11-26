# 2dccc8fa · glibc D1 rtld 文件采样拒绝

2026-11-26 · 基线 `3be3c442`，源码改动 `2226fd1e`。XOS 当前 `mmap` 只提供私有匿名保留。glibc 2.44 通用 `elf/dl-profile.c:387` 依赖可写共享文件映射，用于多个进程在同一个文件中累计 `LD_PROFILE` 数据。这个映射没有 XOS 后端。D0 另要求首批动态启动限制加载器环境、固定闭包并采用 eager binding。 [D0 契约](../contracts/dynamic_linking_d0.md)

## 上游构建与调用边界

显式 `--disable-profile` 在实际 XOS 配置中得到 `build-profile = no`、`build-shared = yes` 和 `build-pie-default = yes`。`configure.ac:220` 与 `Makeconfig:1176` 用该开关控制带采样的静态 `.op` 和 `libc_p.a`。`elf/Makefile:139` 仍把 `dl-profile` 列入 rtld，未修改基线的 `elf/dl-profile.os` 依然报 `MAP_FILE` 未声明。

- `rtld.c` 在启动重定位选中 `dl_profile_map` 时调用 `_dl_start_profile`。`dl-open.c` 在后续重定位第一次选中对应映像时也调用它。XOS 在该入口发出致命诊断，拒绝实际启用采样。采样文件没有打开、创建或映射操作。
- `rtld.c` 在只读全局表中保留 `_dl_mcount`，`dl-runtime.c` 的共享 PLT 审计路径也会调用它。上游在采样未启用时直接返回，XOS 保留该行为和已有隐藏别名。上游 `elf/Versions` 把该符号列在 `GLIBC_2.1`，当前 XOS 生成的 `ld.map` 将它归入现有 `GLIBC_2.44` 节点。最终共享链接仍待验证。
- D0 启动链仍需限制 `LD_PROFILE` 和 `LD_PROFILE_OUTPUT`，包括在目标未匹配时阻止其参与选择或触发特殊 PLT 配置。独立的 `sprof` 工具也需要只读文件映射，未纳入本轮 rtld 构建。 [D0 环境边界](../contracts/dynamic_linking_d0.md#4-依赖闭包搜索与输入预算)

## 实际构建

断网 Linux arm64 下，最多两个构建任务，GNU glibc 2.44 原包均经仓库信任材料验证签名。XOS 交叉 GCC 16.2.0、binutils 2.47。两轮的输入回执中只有 `dl-profile.c` 覆盖层有差异。

先用 `scripts/probe_glibc_rtld.py --archive "$GLIBC_ARCHIVE" --jobs 2 --output "$PROOF"` 准备已验签和已打补丁的源码。以同一回执中的交叉编译器、环境与 `configure_shared` 参数另建干净配置目录 `shared`，并显式追加 `--disable-profile`。沿用 `configparms` 的 `ASFLAGS += -Wa,--divide`。实际目标为：

```sh
for header in rtld-sizes.h sem_t-align.h cpu-features-offsets.h \
              features-offsets.h link-defines.h tlsdesc.h rtld-offsets.h; do
  make -j2 -C "$source/csu" objdir="$shared" "$shared/$header"
done
make -j2 -C "$source/elf" objdir="$shared" "$shared/elf/dl-profile.os"
make -j2 -C "$source/elf" objdir="$shared" "$shared/elf/ld.so"
```

改动后的 `dl-profile.os` 是实际 `-fPIC -DSHARED` 编译的 x86-64 `ET_REL`。`_dl_start_profile` 的唯一未定义符号是 `__GI__dl_fatal_printf`。上游实际 `dl-printf.os` 提供该符号并调用 `_exit(127)`。`rtld.os`、`dl-open.os` 和 `dl-runtime.os` 保留指向上述入口的重定位。两轮静态 `dl-open.o` 与 `dl-runtime.o` 的各自 `.text` 均逐字节一致。

用 x86-64 Linux 宿主测试单独链接实际 `dl-profile.os`，宿主测试提供诊断函数。未启用采样时，计数入口直接返回，宿主进程继续并以 0 退出。启用调用输出预期诊断并以 127 结束。两个进程都未创建采样文件。该测试覆盖目标对象和诊断交接。客体解释器启动仍待验收。

直接 `ld.so` 目标越过文件采样错误，停在 `sysdeps/xos/dl-sysdep.c:5` 的原生解释器启动保护。继续构建还需 `libc_pic.a`。由上游顶层规则构建该归档时，首个源码错误来自通用 `io/fstatfs.c:32`，其 `weak_alias` 目标名 `__fstatfs` 与头文件的隐藏声明不匹配。归档构建在打印该错误后达到 75 秒上限。直接重试上游 `io/fstatfs.os` 以状态 2 复现该错误。完整 `ld.so` 未链接。

| `build/profile-evidence/` 中的工件 | SHA-256 |
| --- | --- |
| `base/compile-dl-profile.log` | `85664715093d9e0fc9947da3a8fc2d2a9dc0ba507d5376bed82fc9eb239c4b6f` |
| `selected/prepared/manifest.json` | `3197893fd3220429dd1710e293d93ff5d525d9e2b47146037800ef8d102d4dbb` |
| `selected/prepared/source_verification/report.json` | `e3aad9d790cf00702927aa5d74ef98cfbc6580f79382ae520b22da696fe5a34a` |
| `selected/shared-no-profile/elf/dl-profile.os` | `8ec81e467f30b3b0da5df0d7aea0e92c1c8cbad02c17b093a0ab8c64ea3b0a4e` |
| `selected/shared-no-profile/elf/rtld.os` | `8d567d4cbf514edfd033bfe651b19f09bf26bca6e236bfad093d8e185a275de3` |
| `selected/shared-no-profile/ld.map` | `a011893267acbde60230b730cd909d46f3937589fa66e73815b962c02d7ad6e7` |
| `selected/make-ld-so-no-profile.log` | `f29c42102cd3019e794a5bc09350a4bd70dce0a95d02eae95be823812a10c8f6` |
| `selected/make-ld-so-keep-going.log` | `986568552cdfbf24d3a03450aa8b246e609e548c9c21366079fdd1f9cb477a06` |
| `selected/make-libc-pic.log` | `0fcf0cd69b5d66969417ebb748d4f226897b1cf0de8aedac9e1cfa17277e7d96` |
| `selected/make-fstatfs-os.log` | `369c2f18102eb8c88a94c5d4f56e60134ba6d7a371b623e1e8f6d451dce734b9` |
| `static-text-comparison.log` | `a7fa51280823fc597e26af3764adf4b5ec1466f7a91861436028bf4ec98c7264` |
| `runtime-probe/run.log` | `e91fa6d49eb962a1f31224d1156da326cc895713881bd8b86dc1c9222b95217b` |
