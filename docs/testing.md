# 自动化与现场验收

在仓库运行 `uv sync --frozen --python 3.12 --extra test`、`uv run pytest -q`。单元测试覆盖 RAW 大小写与扩展名、冲突、非法文件名、路径逃逸、hardlink/reflink/copy 回退、取消保护、稳定检测、100MiB、哈希版本、历史保留、SQLite 重启、401/403/404/429/5xx、网络中断、上传结果未知与管理认证。

真实容器测试脚本 `scripts/integration.py` 只能用于名称以 pixcake- 开头的全新测试容器和合成数据目录。不要指向业务实例。先以固定版本 AIO 启动容器，并将 `<fixture>/proofs` 挂载到 `/external-media:ro`，设置 PORT=3000、EXTERNAL_MEDIA_ROOT=/external-media，端口只绑定 127.0.0.1。命令：

```sh
uv run python scripts/integration.py --container pixcake-ci-picpeak --root /tmp/pixcake-fixture --count 100 --report integration-report.json
```

1000 张测试需要另一个全新实例和目录，传 `--count 1000`。脚本用一次性管理员仅设置测试环境，再生成 read/write Token；Bridge 本身始终使用 Token。流程：50 选中、追加 5、取消 2、进入 EDITING 后取消、导出 53 张成片并返修一次、检查 54 次交付、停止 PicPeak、恢复、重建 Bridge 引擎、校验无重复与所有 RAW SHA-256 不变。断网以客户端连接失败测试；真实 NAS 断电尚未执行。

中文检查：在中文 Fork 运行 `node scripts/check-zh-cn.mjs` 与 `node --test scripts/check-zh-cn.test.mjs`；前端类型检查、完整 Vitest 和 AIO 构建见维护文档。API 中文客户姓名有独立真实验证器测试。

浏览器自动化的桌面 Chrome、移动视口 Chrome、iPhone WebKit 和微信 UA 测试不能替代真机。现场在 iPhone Safari、Android Chrome、微信、Chrome/Edge 检查匿名分享、密码、中文字体、精修标记新增/取消、评论、加载更多、下载、弱网恢复。至少两位不同客户共同选择，以核实标记合并语义。

像素蛋糕：先打开含 50 张 RAW 的项目，Bridge 再加入 5 张。观察是否实时发现；否则记录版本和“刷新/重新导入目录”的操作。导出保持 stem 和 EXIF 到 04_FINAL，等待稳定窗口后检查客户原链接的新图及再次导出的返修。

fnOS：检查 UID 1001 只读 RAW/FINAL、可写 selected/history；重启 NAS/Bridge/PicPeak；恢复数据库与历史备份；模拟断网并确认重新联网后不重复上传；原 RAW 整批 SHA-256 前后必须完全一致。
