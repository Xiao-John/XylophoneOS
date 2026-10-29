# 0086 Modern Platform Phase 2：网络维护者交接

2026-10-29。独立分支 `codex/modern2-network-handoff`，基于本轮fetch的upstream
`aaec2e9d8ffe61ce1d523cd56852d36cde3edd07`。网络仅文档；与PX4-A和Python不同worktree，
不占用公共build/内核/共享头/SDK/驱动/浏览器文件，不修改原工作区或日常LocalPilot安装。

## 选择、完成内容与边界

公开PR #18尚未合入，故按用户明确要求保持N2 BLOCKED，不实现或调用112，不自批/合并。
PR #17已合入；#18–#21仍Draft/open，公开reviews、threads、comments为空。PR #21 HEAD
确认 `c152f7f`。快照采集于北京时间19:54，状态可变，实施前须再次检查。

[审查包](../reports/modern2_network_20261029/README.md)固定18份提交文件与Git blob/哈希，
新增具体待审决策：未启动grant与活体撤销歧义、INFO/grant布局/数值、复制副作用原子性、token代际、
N1从pre-run到运行期IRQ的缺口、reset timeout quarantine未验和客户端IPC契约。
验收矩阵细化D1–D3、真实ETH→ARP→IPv4→TCP→HTTP→原解析器/liteHTML画面；
要求guest request_nonce、host处理时fresh response_nonce、PCAP TCP重组、字节摘要和同run真实截图。
这些是设计/静态审查结论，不是新网络资格或公共接口分配。

## 实际验证

从提交内 `git show REV:PATH` 读取18份原提案/驱动/契约/收据，与checkout逐字节比较，
保存字节数、SHA256、Git blob、提交和PR映射；18/18相同。原N1/B1来源未改。
运行命令在本worktree：

```sh
python3 tests/docs_consistency.py
python3 tests/abi_doc_consistency.py
git diff --check
```

原始输出保存在[checks目录](../reports/modern2_network_20261029/checks/)；检查成功只证明文档/ABI登记
一致性，不证明N2运行。无运行时代码或许可证组件变更，因此没有重建系统或重跑旧QEMU。
所有新客体D/N2/TLS项目NOT_RUN/BLOCKED；没有可报告的新SDK/ELF/镜像/QEMU argv或内存/资源数。
不将原N1的34 DMA页和旧回归重绑到新main。

## 下一位负责人

先由维护者在原PR #18审查并解决明确的契约决策、合入claimed登记；设备负责人再独占实现
共享头/dispatch/生命周期/两个SDK与manifest，真实通过D1–D3。用户态网络服务再接固定lwIP2.2.1，
先numeric host+显式IPv4完成真实HTTP，最后接Aurora；DNS/DHCP、TLS、DOM/Worker/WASM各自独立。
本docs PR不能充当维护者对PR #18的批准，也不解锁本轮最低真实公共兼容能力成功标准。
