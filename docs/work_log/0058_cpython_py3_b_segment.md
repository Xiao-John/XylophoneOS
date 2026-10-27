# 0058：CPython PY3 B段收口

2026-10-27。用户授权继续完成CPython PY3 B段。只接入B2墙钟/时区、B3 SQLite与B4
压缩模块；不改dash端口，不重建或更新1026正式发布资产，不提交工作树。

## 交付范围

- B2：CMOS RTC提供启动UTC样本，PIT提供之后的单调增量；`CLOCK_REALTIME`、
  `gettimeofday`、POSIX TZ规则和ZoneInfo可用。锁定tzdata 2026.5 wheel作为ZoneInfo
  数据fallback。QEMU启动显式设置`base=utc,clock=host`。
- B3：SQLite 3.54.1静态模块及XOS VFS。覆盖建库、事务提交/回滚、唯一约束、busy、
  损坏输入，以及`sync`、重启、重开、完整性检查和数据持久化。
- B4：静态内建`_bz2`、`_lzma`、`_zstd`，分别绑定bzip2 1.0.8、xz/liblzma 5.8.4、
  zstd 1.5.7。覆盖流式roundtrip、损坏/截断输入、257字节输出上限及进程资源回收。

SQLite范围限定为单进程、每库单个可写连接和rollback journal；没有WAL、共享内存或
跨进程锁。VFS在EOF前检查文件长度，避免FatFs越界seek扩展文件。墙钟在启动时采样RTC，
之后依赖PIT；虚拟机暂停/挂起期间不承诺独立刷新RTC。B4只证明上述库和Python API，不
表示归档工具或完整压缩生态已移植。全部组件仅本地验收，未公开分发。

## 构建与客体验收

为吸收更新后的`licenses/components.json`，在独立输出目录构建系统：

```text
python3 scripts/build.py --output-dir build/cpython_py3_b_segment/system_final
```

结果：build ID `6251d26b611a388d`，镜像`xos.img` SHA256
`cc5524eb0b57a528f5db973e888b18356ecb5caf16ed767a604a221064d844d0`。
CPython fingerprint `11c39c52e451a9499450`，stage含1199个文件，静态扩展为
`zlib`, `_sqlite3`, `_bz2`, `_lzma`, `_zstd`；stage manifest SHA256
`74f45b5baa1be78a5d252d608bd2dcbb526da3b91113c4e61a8e1abba104e4a6`。

针对同一新系统镜像和同一CPython stage，依次运行：

```text
python3 tests/cpython_py3_b2_smoke.py --work .cache/xos_seed/cpython/11c39c52e451a9499450 --image build/cpython_py3_b_segment/system_final/xos.img
python3 tests/cpython_py3_b3_sqlite_smoke.py --work .cache/xos_seed/cpython/11c39c52e451a9499450 --image build/cpython_py3_b_segment/system_final/xos.img
python3 tests/cpython_py3_b4_smoke.py --work .cache/xos_seed/cpython/11c39c52e451a9499450 --image build/cpython_py3_b_segment/system_final/xos.img --compression-report .cache/xos_seed/cpython/compression/fb1e916af22be55064de/report.json --report .cache/xos_seed/cpython/compression/guest_report_b4_11c39c52e451a9499450.json
```

三份guest gate均为`passed`。B2客体墙钟位于宿主UTC采样窗口内，POSIX DST与ZoneInfo/tzdata
通过，前后资源计数均为`[130336,2,0]`。B3的创建/事务/约束/busy/损坏和sync/重启重开/
完整性检查两项均通过。B4三种流式与损坏/截断/限额检查、进程退出及资源回收均通过。
对应报告为`build/cpython_py3_b2_report.json`、
`.cache/xos_seed/cpython/sqlite/guest_report_11c39c52e451a9499450.json`及
`.cache/xos_seed/cpython/compression/guest_report_b4_11c39c52e451a9499450.json`。

其他检查：`python3 scripts/license_audit.py --build build/cpython_py3_b_segment/system_final`
通过（7份材料；逐成员许可审查仍未完成）；`python3 tests/abi_doc_consistency.py`通过当前
ABI表；`git diff --check`通过。

## 许可和文档

`licenses/components.json`登记tzdata、SQLite、bzip2、xz/liblzma及zstd及其许可摘要。
许可原文、源码锁定和端口材料保存在`src/ports/cpython/`。这些材料检查不代表逐成员法律
审计，也不代替未来发行包复核。更新`docs/licensing.md`、`docs/decisions.md`、
`docs/cpython_py3_options.md`、`docs/xos_plan.md`和`docs/state.md`。

记录编号0057已被现存的PR #3冲突审查占用，本记录使用0058；没有覆盖0057。未运行完整
POSIX、VM挂起恢复校时、SQLite WAL/跨进程压力、完整压缩生态或公开发行检查。工作树中
其他先存改动保留，不提交、不推送。
