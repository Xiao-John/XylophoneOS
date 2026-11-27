# a569d3a6 · Pumpkin 同域镜像的换版与回切演练

在两个独立 ext4 测试卷上，用不同 Linux UID 运行真实操作者和代际提供者。
已冻结的系统 `2ba0a3070e1d8753` 发放原凭据，写入修订 3 并提交到独立
代际根。三种两端绑定不一致的组合均被拒绝，工作盘及代际记录字节保持。

在同一块工作盘上引导同域候选 `fbe70625e73497ca`，它用原凭据建立并退出
会话，读回修订 3 的资源，随后提交修订 4。切回原镜像后，原凭据从同一工作盘
读出修订 4 的资源。工作盘 inode 保持，凭据内容保持，独立代际确认当前修订。
两个构建的 ISO 字节不同。两张镜像中所核对的六个文件服务与 Pumpkin 程序
对应字节相同，本次覆盖同格式兼容性。

在 Linux arm64、断网 QEMU 11.1.3 TCG 上完成两次演练，11 项检查均通过。
以 ID 各自对应的系统 manifest SHA-256 调用新增入口。参数所指的工作目录
和代际文件目录分别位于可实际执行 Linux 权限的隔离 ext4 测试卷。

```sh
TMPDIR="$OPERATOR_FILESYSTEM" python3 -B tests/pumpkin_image_transition_guest.py \
  --current "$CURRENT_SYSTEM" --current-sha256 "$CURRENT_MANIFEST_SHA256" \
  --replacement "$REPLACEMENT_SYSTEM" --replacement-sha256 "$REPLACEMENT_MANIFEST_SHA256" \
  --provider-filesystem "$PROVIDER_FILESYSTEM" --output "$REPORT"
```

测试夹具在一次性目录中替换操作者标记并重新启动独立提供者。生产修改须使用
有授权的两端维护流程，生产切换控制器、其中断恢复、存储格式演进与物理断电
仍各有验收门。
[演练回执](../reports/pumpkin_image_transition_20261127/manifest.json) ·
[部署契约](../contracts/pumpkin_provider_deployment.md)
