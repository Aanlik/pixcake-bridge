# 本机验证记录

基线：PicPeak v3.134.1，官方 stable SHA `5fc54d9a5e17a7f054c926922a6f820f3c98eda2`；Bridge v0.1.0，Python 3.12。测试日期：2026-10-07。

真实 AIO 容器完成 100 和 1000 张合成照片两组测试。每组 50 初选、追加 5、SELECTING 取消 2、EDITING 再取消保留 RAW，53 个成片加一次返修共 54 次上传。photo_id、客户评论/评分/喜爱/绿色标记、文件名排序与分享入口保留。停止 PicPeak 后恢复、同 SQLite 状态重启引擎，没有重复上传。全部 100/1000 个 RAW SHA-256 不变。完整无凭证报告位于交付目录 verification/real-picpeak-results.json。

中文键检查 6331，复数键 196；检查器故障测试 5 项通过。前端完整测试首次 135 个文件、879 项通过，随后增加中文日期测试单独验证。Docker AIO 与 Bridge 已在本机实际构建。

最终回归结果与浏览器截图见交付目录 verification。真机/微信、fnOS、FN Connect、像素蛋糕以及物理断电尚未完成。
