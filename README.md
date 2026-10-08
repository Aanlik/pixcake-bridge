# PicPeak 简体中文 + PixCake Bridge 一体化版

为飞牛 fnOS NAS 提供中文客户选片、NAS 照片目录关联、待精修 RAW 整理和精修成片交付。默认使用 **一个 Docker 镜像、一个容器**；PicPeak 和 Bridge 保留独立代码、进程和数据库，便于跟随官方更新。

当前固定镜像：`picpeak-pixcake:3.134.1-zh.6-bridge.0.1.1`。
包含 PicPeak 3.134.1 中文版及本轮中文审校，Bridge 0.1.1。不要使用 `latest`。

## 工作流程

相机 RAW/JPG → NAS → 客户中文选片（选为精修）→ `03_SELECTED_RAW` → 像素蛋糕 → `04_FINAL` → 自动替换客户页面上的原照片。

Bridge 按 `source_filename` 匹配原片，等待成片稳定后计算 SHA-256；同名返修再次同步，保留原 photo_id、评论、评分、选片和分享链接。默认保留最近 3 个成片版本。SELECTING 阶段取消可清理待精修副本，EDITING 后取消仅标记，支持后续追加。原片始终只读。RAW 支持 ARW/CR3/CR2/NEF/RAF/DNG/ORF/RW2；第一版成片支持 JPG/JPEG/PNG，默认单文件 100 MiB，要求文件 stem 唯一一致。

## 一体化结构

- PicPeak 页面：容器端口 3000，内置前端和后端，默认 SQLite。
- Bridge 中文管理：容器端口 8080，仅绑定 NAS 内网 IP。
- 容器内通过 `127.0.0.1` 通信，使用 Public API Token，无需管理员密码。
- `/data` 保存 PicPeak 数据、媒体、JWT 密钥和备份；`/bridge-data` 保存 Bridge SQLite。
- Supervisor 分别监控两个进程；进程异常自动重启，Docker 健康检查覆盖已启用的两个服务。
- 开启同步后，一个服务故障会让整个容器显示 unhealthy。Docker 的 restart 策略不会因 unhealthy 自动重启；应查日志处理，不能把健康检查当作自动修复。
- 两个服务升级、容器重启时会同时短暂中断。

## 飞牛部署

### 1. 准备目录

每个摄影项目使用：

```text
摄影项目/项目名/
  01_RAW/
  02_PROOF/
  03_SELECTED_RAW/
  04_FINAL/
  05_HISTORY/
```

确认真实 NAS 绝对路径，给 UID/GID 1001 读取 RAW、PROOF、FINAL 和写入 SELECTED、HISTORY 的权限。镜像只调整数据卷权限，不会自动修改摄影目录权限。通过 Docker 的只读挂载保护原片；不要可写挂载整个 Camera 或摄影项目根目录。

### 2. 构建或导入镜像

源码放在同一父目录，分别为 `picpeak-zh` 和 `pixcake-bridge`。获取中文 Fork `feat/zh-cn`，然后在 Bridge 仓库运行：

```sh
./docker/integrated/build.sh
```

默认构建 linux/amd64（常见 x86 飞牛 NAS）；ARM NAS 构建时设置 `PLATFORM=linux/arm64`，应另行验收。构建先使用 PicPeak 自己的 Dockerfile，再组合 Bridge。独立执行 Compose build 前必须先构建固定版本 PicPeak 基础镜像。

离线导入：

```sh
docker save -o picpeak-pixcake-amd64.tar picpeak-pixcake:3.134.1-zh.6-bridge.0.1.1
```

在飞牛 Docker 镜像管理中导入 tar，再创建 Compose 项目。

### 3. 首次初始化

复制 `.env.example` 为 `.env`，设置 `LAN_BIND_IP` 为 NAS 内网 IP、`PHOTO_PROJECT` 为项目绝对路径、`PROJECT_FOLDER` 为目录名称、`BRIDGE_ADMIN_PASSWORD` 为至少 12 位随机密码。初次保留 `BRIDGE_ENABLED=false`、`PICPEAK_TOKEN` 为空。

```sh
cp projects.example.json projects.json
docker compose up -d
```

访问 `http://NAS内网IP:3000`，按 PicPeak 初始化向导创建用户名管理员。初次部署的设置令牌保存在持久化 PicPeak 数据中，也可查看 PicPeak 启动日志。此时 Bridge 尚未监听端口，容器健康检查只检查 PicPeak。

完成后，在 PicPeak 设置中创建具有 read/write 权限的 Public API Token；填入 `.env` 的 `PICPEAK_TOKEN`，设置 `BRIDGE_ENABLED=true`。创建选片项目并确认其数字 event_id；修改 `projects.json` 中的名称、event_id 和四个容器路径。

```sh
docker compose up -d --force-recreate
```

访问 `http://NAS内网IP:8080` 查看 Bridge 管理后台，用已配置的 Bridge 管理密码登录。手动同步并确认连接状态。每次修改项目配置或环境变量后重建容器。

### 4. 关联 NAS 照片

新建或管理项目时选择“关联 NAS 文件夹”，用 External Media Reference Mode 引用 `/external-media/项目名`。PROOF 挂载只读。引用既有 Home/Camera 时设置 `NAS_CAMERA_ROOT` 并使用：

```sh
docker compose -f compose.yaml -f compose.nas-camera.yaml up -d
```

在页面选择具体拍摄文件夹，避免把全部 Camera 导入同一项目。RAW 与待精修、成片目录仍按项目配置独立挂载；Camera 入口不会自动替代 RAW 映射。

### 5. 像素蛋糕与客户分享

像素蛋糕读取 `03_SELECTED_RAW`，导出到 `04_FINAL`，保留原文件 stem。目录追加 RAW 后若软件不能自动识别，刷新或重新导入目录。

客户入口仅转发 PicPeak；Bridge 不对公网开放。FN Connect 可用于摄影师远程管理，但不能作为已验证的匿名客户分享入口。临时可使用独立 HTTPS 穿透入口，之后迁移公网 IP + DDNS；从现在使用固定自有域名，设置 PicPeak 站点地址，尽量保留已有分享链接。原片上传、Bridge 同步均不依赖公网。

## 从双容器迁移

先停止原 PicPeak 和 Bridge，再备份两个完整数据卷、`.env`、projects.json 和 Compose。新容器沿用原 PicPeak 卷挂载 `/data`，原 Bridge 卷挂载 `/bridge-data`；照片目录的容器路径必须保持一致，已有项目路径不能随意改名。必要时在 Compose 中用 `external: true` 和真实 `name` 引用原卷，避免 Compose 项目名称改变后创建空卷。

第一次迁移应在卷副本上验证，确认 photo_id、评论、分享链接、Bridge 同步记录和 RAW 校验后，再替换正式容器。不要同时运行新旧同步服务，不要覆盖真实 Token。备份完整 `/data`，仅备份数据库会遗漏 JWT 密钥与媒体。

## 后续统一更新与发布

1. 在中文 Fork 同步 upstream stable，解决 locale/中文 UX 的窄范围冲突，执行翻译、前端、Docker 检查。
2. 在 Bridge 更新依赖和测试，记录两个仓库的确定提交与版本。
3. 更新 `build.sh`、Dockerfile、`.env.example`、Compose 和 README 的固定镜像版本。
4. 构建一体化镜像，验证两个进程、初次禁用 Bridge、启用后健康检查、重启恢复以及选片→成片→返修流程。
5. 发布唯一版本标签，部署前备份完整数据卷；更新只替换镜像，保留卷和照片挂载。
6. 回退涉及数据库迁移时，恢复升级前卷备份；不能只切换旧镜像并假定数据库兼容。

GitHub Actions `Integrated image` 检查锁定中文 Fork 提交并构建一体化版，执行双服务与重启检查。手动执行时可选择发布到 GHCR；发布账户权限、仓库包访问权限仍需正确配置。旧双容器示例保留为 `compose.dual.yaml`，说明见 [双容器部署](docs/deployment-dual.md)。

## 测试与限制

见 [测试计划](docs/testing.md)、[原工作流验证](docs/verification.md)、[一体化验证](docs/integrated-verification.md)。真实设备浏览器、FN Connect、像素蛋糕自动发现及 ARM 支持分别验收，不能用容器启动测试代替。PicPeak 可连接外部 PostgreSQL；Bridge 通过 SQLAlchemy 保留迁移路径，需额外安装 postgres 可选依赖并执行数据迁移，不是改连接字符串即可完成。
