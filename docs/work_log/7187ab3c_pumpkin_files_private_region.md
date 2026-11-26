# 7187ab3c · Pumpkin files private region

2026-11-26 · 从 `a37ecacc` 实作 [files 私有存储区域](../contracts/pumpkin_files_private_region.md)。
专用构建使用内核已有的 files 块权利，校验工作盘 FAT32 前缀和两片各 9 扇区的无路径
槽。普通文件 I/O 与 block benchmark 共享前缀上界。原有 kernel、公开 file v2 与
冲突路径规则未修改。读写仅在 files 内部，测量数据为固定测试字节。

## 验证

用 x86_64-elf GCC 16.2.0、Python 3.12.15 和 QEMU 11.1.2 从当前源码构建两套
系统与绑定探针。dash 0.5.13.5 由锁定归档对同一个隔离系统 SDK 重建。

```sh
python3 scripts/build.py --files-private-storage-probe --output-dir build/pumpkin_private_region/final_system
python3 scripts/build.py --output-dir build/pumpkin_private_region/final_ordinary
python3 scripts/build_pumpkin_daemon.py --storage-probe --sdk build/pumpkin_private_region/final_system/sdk --output build/pumpkin_private_region/final_fixture
python3 scripts/build_pumpkin_daemon.py --storage-probe --sdk build/pumpkin_private_region/final_ordinary/sdk --output build/pumpkin_private_region/final_ordinary_fixture
python3 scripts/build_dash.py --sdk build/pumpkin_private_region/final_system/sdk --archive "${XOS_DASH_ARCHIVE}" --receipt build/pumpkin_private_region/final_dash.json
python3 tests/pumpkin_private_region_guest.py --system build/pumpkin_private_region/final_system --ordinary-system build/pumpkin_private_region/final_ordinary --fixture build/pumpkin_private_region/final_fixture --ordinary-fixture build/pumpkin_private_region/final_ordinary_fixture --dash-receipt build/pumpkin_private_region/final_dash.json --output build/pumpkin_private_region/final_guest
```

隔离格式执行三次开机，来宾同步后宿主以 SIGKILL 结束 QEMU 并读取完整尾部。
首次 xsh 写入公开测试文件，尾部仅槽 0 已写入。第二次由 dash 验证前次公开文件，
尾部两槽均完整。第三次由 xsh 再读，尾部与第二次逐字节相同。普通进程对尾部的
块读写被拒，目录查询正常，普通路径上的文件可写可读。三次进程资源均恢复到
`129713 / 3 / 1`。普通系统在未扩展 FAT32 工作盘上通过对照，资源为
`129714 / 3 / 1`。

损坏布局标识、FAT32 重叠及公开容量不足三种客体均在启动时拒绝，无私有区域写入。
初次测试错误地等待非法盘上的 `sync` 进入 files，实际先被监督器的恢复门拒绝。
最终 runner 分别核对启动的 files I/O 错误、维护门拒绝和测试盘尾不变。ABI 一致性
检查通过。

| 工件 | SHA-256 |
| --- | --- |
| 隔离系统 `799f64d0efca79f8` manifest | `1b38c079a70147a64f722e9b04ddcdcddf63cdbd4ba95ddebd72cd6a10d98371` |
| 隔离系统 ISO | `f8764f0f1e9d512cc9d0d9a5273a81926cec0e75b58272b44c067dc21b3e99f6` |
| 隔离 SDK 树 | `0c65d43518e2c2eff3b9e24b1e57d6510df6e00621d5a49701bd5d067440a578` |
| 普通对照系统 `ad6df9491f8466a3` manifest | `d854426595df77bb31e58de1e3a0c428ce8db391de0ec530474f22dfff418363` |
| 探针 ELF | `40ec47857fe16d5713ee1d2d142211c9ed00c0d57afac13dec7df3d15b3901e2` |
| dash ELF | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| `build/pumpkin_private_region/final_guest/report.json` | `cbe3b18f8bf5f4b508923fcc89e550f814af5f1199d871d5e5d27f63ff1d29cb` |

报告保留七项核验结果、工件及资源。客体串口日志均在报告同目录。物理断电、写入中
断、真实独立发布记录及跨进程写权限未验。下一阶段需先冻结受信调用者授予，再接入
单写者发布与独立防回滚代际来源。
