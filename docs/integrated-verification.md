# 一体化镜像验证

## 当前固定版：zh.18 / Bridge 0.1.5

2026-10-09，linux/amd64，镜像 `picpeak-pixcake:3.134.1-zh.18-bridge.0.1.5`，镜像标识 `sha256:1d97c50f4735b0562afe739ee530dd42cec9e444cec536e9595aa606f586cdd0`，PicPeak 中文 Fork 提交 `a9bd2d984ec00d663ee1a3764e0bd4c2564adec1`，Bridge 发布版本 0.1.5。

- PicPeak AIO 本地镜像编译、Bridge 66 项测试、两服务启动、Bridge 进程恢复、整容器重启和状态卷保留检查通过。
- 本轮 PicPeak 前端生产构建、中文 locale parity、返修流程前端测试、7 项返修 API 测试及 ESLint 检查通过。
- NAS 导入包：`picpeak-pixcake-amd64-3.134.1-zh.18-bridge.0.1.5.tar`，SHA-256：`66412f4001d383e6e26ead85f50c8367ad1c81e74a231f180adb8ce18ddddcaf`，246 MiB。该包现位于项目交付目录的 `outputs/`。

本机容器构建与启动检查已通过；飞牛 NAS 实际切换和页面验收仍在本次部署流程中。

## zh.17 历史验证

2026-10-09，linux/amd64，镜像 `picpeak-pixcake:3.134.1-zh.17-bridge.0.1.4`，PicPeak 中文 Fork 提交 `6a5494e0b3759e408f2a8ffb3bbe6603f1dcfd9c`，Bridge 版本 0.1.4。

- 中文完整性检查通过：4812 个键、190 个复数键；386 个文件中的 4632 个静态翻译引用检查通过。
- NAS 导入包 SHA-256：`1d062d8c101f1cf23889419a12b105624004a32da3e7d051a1ab35e3ec4683ac`，246 MiB。

本地构建和隔离容器验证不等同于 NAS 安装或真实客户浏览器验收。更新时保留原有 PicPeak 与 Bridge 数据卷、Camera 只读挂载、交付目录和 `.env`；导入镜像后使用此处固定标签更新 Compose，再用测试项目检查选片按钮和状态。

## zh.16 历史验证

2026-10-09，linux/amd64，镜像 `picpeak-pixcake:3.134.1-zh.16-bridge.0.1.4`，镜像 ID `sha256:af602c683402ecb17328c24e3e854dc8bfcc61c9462cfdd7af32b719eb60cab0`。PicPeak 中文 Fork 提交 `8a1142bb79df04f0e922b3fb0ccaf37b10955f18`，Bridge 版本 0.1.4。

- PicPeak 前端生产构建、类型检查、客户流程定向测试 5 项、后端选片和需求路由测试 9 项、i18n CI 检查全部通过；Bridge 测试 64 项全部通过。
- 新增客户单张“选为精修 / 已选精修”与已交付照片“返修与新增需求”操作；多选时可批量标记精修。绿色工作流标记可在绑定 Bridge 后独立于通用反馈开关使用。
- 返修和新增需求不依赖通用评论开关，不要求客户填写邮箱。
- 一体化容器 smoke 验证通过：PicPeak 与 Bridge 同容器启动，Bridge 进程异常恢复，PicPeak/Bridge 数据卷重启保留；未配置 API Token 时初始化入口仍可用。
- NAS 导入包：`releases/picpeak-pixcake-amd64-3.134.1-zh.16-bridge.0.1.4.tar`，SHA-256：`f1a763aa83f3e659cbad308cae1987e3d1a1a97ec02dd0556751d3385e4ee1bf`，246 MiB。

这只是本地构建和隔离容器验证，本轮尚未导入用户 NAS，也未在真实客户分享页或手机/微信浏览器验收。实际 NAS 更新时保留原有 PicPeak 与 Bridge 数据卷、Camera 只读挂载、交付目录和 `.env`；导入镜像后更新 Compose 固定标签，再检查 Bridge 已连接并在测试项目中验证按钮和状态。

## zh.14 历史验证

2026-10-09，linux/amd64，镜像 `picpeak-pixcake:3.134.1-zh.14-bridge.0.1.4`。PicPeak 中文 Fork 提交 `3a4beae15025dc030db8074b50994f83fed4adcd`，Bridge 提交 `c5d8b2a4f3df14fff85b57d5ba190e298e211154`。

- 一体化镜像构建成功；容器启动、PicPeak 与 Bridge 健康检查、Python 3.12、进程异常恢复、整容器重启及 Bridge 状态卷保留均通过。
- 未配置 API Token 时 PicPeak 初始化与健康检查通过。
- PicPeak 定向后端测试 7 项、客户/摄影师前端测试 3 项、Bridge 全套测试 61 项通过。
- PicPeak 前端类型检查与生产构建通过；简体中文 4792 个键、178 个复数键和插值变量检查通过；翻译引用检查通过。
- Compose 基础文件与 Camera 权限覆盖文件均通过解析。当前 Compose 只映射 PicPeak 端口，Camera 为只读挂载，Bridge 不映射宿主机端口。
- NAS 导入包：`picpeak-pixcake-amd64-3.134.1-zh.14-bridge.0.1.4.tar`，SHA-256：`5d6cdcfca76a2897aeae22c87e4db9fc830fe52ebc3ad0394fdd01ff9f8e555a`。

容器 smoke 验证了真实 PicPeak/Bridge 进程组合，但未连接客户的 NAS，也未使用真实 Public API Token 执行选片到成片替换的完整容器级 E2E。选片新增/取消、返修版本、RAW 校验、异常与恢复由 Bridge 单元测试及 PicPeak API 集成测试覆盖；真实 fnOS 文件权限、浏览器、像素蛋糕与外网客户入口仍需现场验收。NAS 尚未更新。

## zh.10 历史验证

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
