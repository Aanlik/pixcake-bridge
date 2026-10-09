# 风险与已知限制

- fnOS 已有部署验收，但匿名客户经 FN Connect 访问、不同 NAS 的 ACL 差异、像素蛋糕增量发现、真实手机和微信仍需现场验证；不宣称这些场景已经通过。
- Docker 挂载在容器启动时确定。新增项目需要先创建项目内 PixCakeDelivery，再在 Compose 中增加只针对该项目的可写 bind mount 和映射，并重启容器；Camera/RAW 保持只读。PicPeak 中的自动关联按钮只会在检测到路径匹配的挂载时出现。
- PicPeak 没有替换上传幂等键。响应丢失后通过远端文件名中的 SHA-256 标记确认；无法确认时停在 UNKNOWN，避免自动重复。必须核对远端后手动授权重试。新的 FINAL 也不会绕过旧 UNKNOWN。
- 上传文件名保留原 stem，但加 `.__bridge_<SHA256>`。PicPeak 下载名可能显示此后缀；RAW 映射始终依赖 source_filename。不要手工修改远端文件名，否则失去自动恢复凭据。
- 图像替换保留 photo_id、选择、评论、分享入口；FINAL EXIF 会更新拍摄时间。按拍摄时间排序需要像素蛋糕保留原 EXIF。按文件名排序在自动化测试中保持一致。
- 多位客户的绿色标记由 PicPeak 合并。一个客户取消，而另一个仍选中时，Bridge 继续视为选中。项目阶段单向推进；回退应备份后人工处理。
- PicPeak 简体中文语言文件通过键、复数形式和插值变量一致性检查；这类自动检查不等于逐句翻译审校。本次新增的选片与精修状态用语按摄影工作流校对。
- hardlink 共用 inode。为保护 RAW，只对已经没有写权限位的源文件尝试硬链接；否则直接 reflink/copy。Bridge 从不修改 RAW 权限。Docker 中独立目录挂载可能令 hardlink 返回 EXDEV，复制回退是正常行为。读取选片目录的软件若自行改权限并写入硬链接，仍可能影响原文件；不确定时配置 copy。
- 当前默认 SQLite，单进程单实例。SQLAlchemy 模型与 DATABASE_URL 保留 PostgreSQL 路径，但未完成迁移工具或 PostgreSQL 生产验收。升级模型之前必须备份。
- FINAL 支持 JPG/JPEG/PNG，最大默认 100MiB；RAW 支持 ARW/CR3/CR2/NEF/RAF/DNG/ORF/RW2。同 stem 的多个 RAW、Proof 或 FINAL 都报冲突，不自动猜测。
- 最近 3 个成功版本保留快照；失败/结果未知的快照保留以便排障，需要监控空间。断电遗留 `.bridge-tmp` 文件会报错，核对后清理再重试。历史目录不能替代 NAS 快照与离线备份。
- 一体化 Compose 只映射 PicPeak 的局域网端口；Bridge 的 8080 仅供同一容器中的 PicPeak 后端访问。PicPeak 需要按管理员账号登录，公开访问应使用 HTTPS。程序无法阻止路由器额外转发端口，部署时仍需避免暴露 NAS 管理端口。
- Public API 出现 401/403 应修复 Token 或权限；429 自动延迟；5xx/网络失败读取可重试，写入不盲目重试。项目远端不可用时不把旧选择当作取消。
