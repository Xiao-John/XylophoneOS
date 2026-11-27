# 73776af5 · Pumpkin 部署镜像的绑定预检

原生启动工具新增 `check-image-update`，在配置的操作者 UID 下用原有启动逻辑
核对两份各自固定摘要的镜像和部署清单。预检对既有状态目录持有与普通启动相同的
独占锁，校验当前安装绑定及工作盘归属，结果用 `bindings_compatible` 表示。
此路径无需连接独立提供者或启动 QEMU。
[操作与边界](../contracts/pumpkin_provider_deployment.md#检查候选镜像的宿主绑定)

断网 Linux 容器以 UID 22101 执行 `tests/pumpkin_image_update_host.py`。
同一安装域的真实构建 `2ba0a3070e1d8753` 和 `fbe70625e73497ca` 分别提供当前
和候选镜像。此前后者通过独立提供者 ext4 多账户验收。另一真实构建
`71e4bd946dd9e2e1` 提供异域拒绝样本。同域格式变更和替换镜像成员两项拒绝使用
派生夹具。测试使用临时私有状态目录和少量占位工作盘内容，逐次确认目录与文件
身份、大小、权限、修改时间和文件摘要保持，且无提供者套接字。
[多账户验收](85e7a877_pumpkin_deployed_accounts.md)
[15 项阳性及拒绝回执](../reports/pumpkin_image_update_check_20261127/manifest.json)

```sh
python3 -B tests/pumpkin_image_update_host.py \
  --system "$CURRENT_SYSTEM" --replacement-system "$REPLACEMENT_SYSTEM" --other-system "$OTHER_REALM_SYSTEM"
python3 -B tests/pumpkin_generation_authority_host.py
```

本轮实测范围是宿主校验。候选与现有客体的协议、原盘代际连续性和两端切换还待
独立验收。实际切换需要协调 provider 和 operator 的授权及中断恢复。
