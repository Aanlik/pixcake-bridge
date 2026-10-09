# PicPeak 简体中文 + PixCake Bridge 一体化版

面向支持 Docker 的 NAS 与服务器，提供中文客户选片、已有照片文件夹关联、待精修 RAW 整理和精修成片交付。系统不依赖特定 NAS 品牌，也不调用修图软件 API。默认使用 **一个 Docker 镜像、一个容器**；PicPeak 和 Bridge 保留独立代码、进程和数据库，便于跟随官方更新。

当前固定镜像：`picpeak-pixcake:3.134.1-zh.12-bridge.0.1.2`。此版本在 PicPeak 项目概览中提供摄影师工作流入口，并可在 Bridge 工作台绑定 RAW 目录和 NAS 交付目录。

首次安装创建管理员账号后，在“设置拍摄类型”中输入中文名称即可；链接前缀自动生成，也可选择“稍后设置”使用现有类型。已有安装无需重做初始化，更新镜像时保留两个数据卷。
包含 PicPeak 3.134.1 中文版，Bridge 0.1.2。不要使用 `latest`。

客户访问域名或地址在 PicPeak「设置 → 常规 → 客户访问地址」中配置。保存后，后台项目列表、项目详情、复制链接和重新生成的二维码都会使用新地址，现有分享路径与令牌保持不变。若设置项被环境变量锁定，请移除 `FRONTEND_URL` 覆盖并重启后再修改。

## 平台与软件适用范围

| 平台 | 部署方式 | 验证范围 |
|---|---|---|
| 飞牛 fnOS | Docker / Compose | 已有双容器 NAS 验证；本轮一体化尚未迁移到 NAS |
| 群晖 DSM | 设备支持的 Container Manager / Docker 与 Compose | 架构适用，尚未实机验收 |
| 威联通 QNAP | 设备支持的 Container Station 与 Compose | 架构适用，尚未实机验收 |
| 其他 NAS、Linux Docker 主机 | Docker Engine 与 Compose | 一体化 linux/amd64 镜像已在隔离容器验证 |

不是所有 NAS 型号都支持 Docker。当前交付镜像是 linux/amd64，ARM 设备需另行构建和验证。各平台首次安装时需配置真实照片路径、目录权限、端口及 API Token；“通用”不代表在不同 NAS 上可以原样照抄路径。

Photoshop、Lightroom、像素蛋糕等软件通过文件夹接入，通常在 Windows/macOS 修图电脑上运行，不打包进本镜像，也不要求在 NAS 内运行。`PixCake Bridge` 是历史项目名称，实际同步机制不依赖像素蛋糕。

## 工作流程

相机 RAW/JPG → NAS → 客户中文选片（选为精修）→ `03_SELECTED_RAW` → Photoshop / Lightroom / 像素蛋糕等修图软件 → `04_FINAL` → 自动替换客户页面上的原照片。

Bridge 按 `source_filename` 匹配原片，等待成片稳定后计算 SHA-256；同名返修再次同步，保留原 photo_id、评论、评分、选片和分享链接。默认保留最近 3 个成片版本。SELECTING 阶段取消可清理待精修副本，EDITING 后取消仅标记，支持后续追加。原片始终只读。RAW 支持 ARW/CR3/CR2/NEF/RAF/DNG/ORF/RW2；第一版成片支持 JPG/JPEG/PNG，默认单文件 100 MiB，要求文件 stem 唯一一致。

## 一体化结构

- PicPeak 页面：容器端口 3000，内置前端和后端，默认 SQLite。
- Bridge 中文管理：容器端口 8080，仅绑定 NAS 内网 IP。
- 容器内通过 `127.0.0.1` 通信，使用 Public API Token，无需管理员密码。
- `/data` 保存 PicPeak 数据、媒体、JWT 密钥和备份；`/bridge-data` 保存 Bridge SQLite。
- Supervisor 分别监控两个进程；进程异常自动重启，Docker 健康检查覆盖已启用的两个服务。
- 开启同步后，一个服务故障会让整个容器显示 unhealthy。Docker 的 restart 策略不会因 unhealthy 自动重启；应查日志处理，不能把健康检查当作自动修复。
- 两个服务升级、容器重启时会同时短暂中断。

## 通用 Docker 部署

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

确认真实宿主机绝对路径。Bridge 以配置的 `BRIDGE_UID`/`BRIDGE_GID` 运行，需有权限读取 RAW、写入待精修目录及历史版本；摄影师账号需能读取待精修目录并写入成片目录。镜像只调整 Bridge 数据卷权限，不会自动修改照片目录权限。Docker 只读挂载保护 RAW、Proof 和成片源文件；不要可写挂载整个 Camera 或摄影项目根目录。

### 2. 构建或导入镜像

源码放在同一父目录，分别为 `picpeak-zh` 和 `pixcake-bridge`。获取中文 Fork `feat/zh-cn`，然后在 Bridge 仓库运行：

```sh
./docker/integrated/build.sh
```

默认构建 linux/amd64（适用于 x86 NAS 或服务器）；ARM NAS 构建时设置 `PLATFORM=linux/arm64`，应另行验收。构建先使用 PicPeak 自己的 Dockerfile，再组合 Bridge。独立执行 Compose build 前必须先构建固定版本 PicPeak 基础镜像。

离线导入：

```sh
docker save -o picpeak-pixcake-amd64.tar picpeak-pixcake:3.134.1-zh.12-bridge.0.1.2
```

在 NAS 容器管理界面导入 tar 并创建 Compose 项目；普通 Docker 主机可执行 `docker load -i picpeak-pixcake-amd64.tar`。此导入操作不需要重新构建镜像。

NAS 无法直接访问镜像仓库时，可运行 GitHub Actions 的 `Integrated image` 工作流并选择发布；成功后会附带 7 天有效的 NAS 导入 tar。导入后在 Compose 配置中使用对应固定版本标签，不要删除 PicPeak 或 Bridge 数据卷。

### 3. 首次初始化

复制 `.env.example` 为 `.env`，设置 `LAN_BIND_IP` 为 NAS 内网 IP、`PHOTO_PROJECT` 为项目绝对路径、`PROJECT_FOLDER` 为目录名称、`NAS_CAMERA_ROOT` 为现有 Camera 绝对路径、`NAS_DELIVERY_ROOT` 为新建的 NAS 交付目录，并设置至少 12 位的 `BRIDGE_ADMIN_PASSWORD`。初次保留 `BRIDGE_ENABLED=false`、`PICPEAK_TOKEN` 为空。交付目录建议在 Home 下单独创建，例如 `Home/PixCakeDelivery`，不要放在原片目录内。

```sh
cp projects.example.json projects.json
docker compose up -d
```

访问 `http://NAS内网IP:3000`，按 PicPeak 初始化向导创建用户名管理员。初次部署的设置令牌保存在持久化 PicPeak 数据中，也可查看 PicPeak 启动日志。此时 Bridge 尚未监听端口，容器健康检查只检查 PicPeak。

完成后，在 PicPeak 设置中创建具有 read/write 权限的 Public API Token；填入 `.env` 的 `PICPEAK_TOKEN`，设置 `BRIDGE_ENABLED=true`。

```sh
docker compose up -d --force-recreate
```

访问 `http://NAS内网IP:8080` 查看 Bridge 摄影师工作台，用用户名 `admin` 和 `.env` 中设置的 Bridge 管理密码登录。在“绑定一个 PicPeak 项目”中填写 PicPeak 项目编号、项目名称和 Camera 下的 RAW 子目录；Bridge 会验证 API 权限与 RAW 路径，并在 NAS 交付根目录创建精修所需目录。项目绑定保存在持久化 Bridge 数据卷中，容器重启不会覆盖。

### 4. 关联 NAS 照片

新建或管理项目时选择“关联 NAS 文件夹”，用 External Media Reference Mode 引用 `/external-media/项目名`。PROOF 挂载只读。引用其他已有照片文件夹时，将 `NAS_CAMERA_ROOT` 设置为该目录的真实绝对路径并使用下面的覆盖文件；文件名中的 nas-camera 是历史名称，适用于其他平台文件夹：

```sh
docker compose -f compose.yaml -f compose.nas-camera.yaml up -d
```

在 PicPeak 页面选择具体拍摄文件夹，避免把全部 Camera 导入同一项目。Bridge 工作台绑定的 RAW 子目录应包含这些 Proof 对应的相机原片。Camera 以只读方式挂载给 PicPeak 与 Bridge。

### 5. 使用任意基于文件夹的修图工作流

通过 SMB 或本地挂载，在修图电脑上访问 `NAS_DELIVERY_ROOT/项目目录/03_SELECTED_RAW` 和 `04_FINAL`。电脑中的路径与容器中的路径可以不同，只要指向同一批实际文件。

| 修图软件 | 获取待精修照片 | 输出成片 |
|---|---|---|
| Photoshop / Camera Raw | 打开待精修目录中的 RAW，按需批量处理 | 保存或导出 JPG/JPEG/PNG 到成片目录 |
| Lightroom | 将待精修照片导入目录／图库；目录追加后按需同步或重新导入 | 设置导出预设，输出到成片目录，保留原 stem |
| 像素蛋糕 | 在 NAS 网络位置打开 `03_SELECTED_RAW`，在像素蛋糕中导入/添加该文件夹 | 将导出位置设为同一项目的 `04_FINAL`，保留原 stem |
| 其他修图软件 | 能读取项目原片并导出所支持的成片格式即可 | 同样遵守输出目录及命名约定 |

例如 `DSC00125.ARW` 对应 `DSC00125.JPG`。第一次在软件里设置输出路径、格式和命名规则后，切换软件通常无需修改 Bridge。若 RAW、SELECTED 或 FINAL 的实际目录改变，仍需修改挂载与项目配置。PSD、TIFF、XMP 等工作文件不属于当前自动交付格式；可以保存在其他工作目录，最终另导出 JPG/JPEG/PNG。

Bridge 不会操作软件的项目、图库或编辑进度。追加 RAW 是否自动出现、取消后是否影响已有软件项目，由软件自身决定；不能将目录同步等同于 PS/LR 项目自动同步。

### 6. 客户分享

客户入口仅转发 PicPeak；Bridge 不对公网开放。FN Connect 可用于摄影师远程管理，但不能作为已验证的匿名客户分享入口。临时可使用独立 HTTPS 穿透入口，之后迁移公网 IP + DDNS；从现在使用固定自有域名，设置 PicPeak 站点地址，尽量保留已有分享链接。原片上传、Bridge 同步均不依赖公网。

## 各平台目录配置

`.env.example` 中的 `/vol1/...` 是飞牛示例，应替换成你实际设备的共享目录路径。群晖可能使用 `/volume1/...`，威联通可能使用 `/share/...`，Linux 主机也可使用自选路径；应以设备实际路径为准。

通过一体化 Compose 与 NAS Camera 覆盖文件时，项目可从 Bridge 工作台绑定，不必逐个改 `projects.json` 或重建容器。输出路径由 `NAS_DELIVERY_ROOT` 共享目录承载，分别建立 `03_SELECTED_RAW`、`04_FINAL` 和 `05_HISTORY`；不要把交付目录放进只读的 Camera 原片目录。创建 PicPeak 相册本身仍不会自动绑定 Bridge，需到项目概览卡片点“打开摄影师工作台”完成一次绑定。

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

见 [测试计划](docs/testing.md)、[原工作流验证](docs/verification.md)、[一体化验证](docs/integrated-verification.md)。群晖、威联通等平台实机、真实设备浏览器、外网分享、各修图软件目录发现及 ARM 支持分别验收，不能用容器启动测试代替。PicPeak 可连接外部 PostgreSQL；Bridge 通过 SQLAlchemy 保留迁移路径，需额外安装 postgres 可选依赖并执行数据迁移，不是改连接字符串即可完成。

NAS 配置文件权限：集成 Compose 首次启动时将只读示例 `projects.json` 复制到 Bridge 数据卷；工作台后续写入持久化卷，重启不会覆盖。Camera 只读挂载用于相册引用和 RAW 匹配；自动选片与精修交付需要在工作台绑定 PicPeak 项目。

Camera 目录权限：若目录仅所有者可读，使用 `compose.nas-camera.yaml` 并将 `NAS_CAMERA_UID` 设置为 Camera 的实际所有者 UID（飞牛常见值为 1000，以实际检查为准）。此覆盖配置仅调整容器内 PicPeak 的运行身份，Camera 仍只读，保留源目录权限。应用后重建容器，再展开 Camera 验证。
