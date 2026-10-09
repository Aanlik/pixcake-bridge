# 一体化镜像验证

## 当前固定版

2026-10-09，linux/amd64，镜像 `picpeak-pixcake:3.134.1-zh.10-bridge.0.1.2`，基于 PicPeak 中文 Fork 提交 `8f05c86b6ce81b57ac5eed2aa14cca542303c766`，Bridge 0.1.2。GitHub Actions [构建与容器验证](https://github.com/Aanlik/pixcake-bridge/actions/runs/37887261907)已通过。

- PicPeak AIO 与集成镜像构建成功。
- 双服务健康检查、Python 3.12、PicPeak/Bridge 数据库创建、Bridge 进程异常恢复、整容器重启和状态卷保留检查成功。
- 未配置 API Token 时 PicPeak 初始化和健康检查正常。
- 手动发布任务导出了 NAS 导入 tar，并保留 7 天。文件 SHA-256：`548b01defdeb6e6fe9d39c8605ac33bd9a1bc7f2515e1146732c4177ad2425dd`。

以上是隔离 CI 容器验证；当前 fnOS 实例的镜像更新仍需导入该 tar 并更新 Compose 项目，不能据此宣称 NAS 已完成迁移。

## zh.9 历史验证

2026-10-09，linux/amd64，本地验证 PicPeak 中文 Fork 提交 `ebe9b52fb3c56c39ee9816706892b055da3c87d1`，Bridge 0.1.1。

镜像 `picpeak-pixcake:3.134.1-zh.9-bridge.0.1.2` 基于 PicPeak 中文 Fork 提交 `ebe9b52fb3c56c39ee9816706892b055da3c87d1`；Bridge 使用 Python 3.12。Supervisor 分别启动 PicPeak 和 Bridge，应用进程以 UID/GID 1001 运行，监督进程为 root。

已通过：
- Bridge 60 项单元与接口测试，包括新增一体化端口、只读挂载检查。
- Compose 解析和部署预检：固定镜像、8080 仅内网、RAW/PROOF 只读。
- 真实一体化容器双服务健康检查、分别创建 PicPeak 与 Bridge 数据库。
- 杀死 Bridge 进程后自动恢复，两个服务重新通过健康检查。
- 未配置 Token 时，Bridge 不监听，PicPeak 初始化与健康检查正常。
- 容器重启后两个服务恢复，Bridge 数据卷中的验证内容保持不变。
- PicPeak 中文改动此前通过 889 项前端测试和生产构建。

测试使用隔离临时容器与虚拟 Token，不修改现有 NAS。双服务健康意味着服务存活，不意味着 Token 已具备真实项目权限；连通性应在 Bridge 管理页面查看。既有 100 张素材选片、成片、返修闭环结果见历史验证文档，本轮未将它重新宣称为一体化实际客户验收。

实际 fnOS 一体化迁移、真实手机、微信、像素蛋糕、公网隧道和 ARM 架构仍需分别验收。官方 AIO 未包含人脸识别 ML 服务。
