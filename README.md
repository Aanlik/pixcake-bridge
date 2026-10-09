# PicPeak 简体中文 + PixCake Bridge 一体化版

面向支持 Docker 的 NAS 与服务器，提供中文客户选片、已有照片文件夹关联、待精修 RAW 整理和精修成片交付。系统不依赖特定 NAS 品牌，也不调用修图软件 API。默认使用 **一个 Docker 镜像、一个容器**；PicPeak 和 Bridge 保留独立代码、进程和数据库，便于跟随官方更新。

当前固定镜像：`picpeak-pixcake:3.134.1-zh.19-bridge.0.1.7`。摄影师和客户都在 PicPeak 操作；Bridge 是同一容器中的内部服务，不单独开放网页端口。

首次安装按 PicPeak 初始化页创建用户名管理员。已有安装无需重做初始化；更新镜像时保留 PicPeak 与 Bridge 两个数据卷。
包含 PicPeak 3.134.1 中文版，Bridge 0.1.7。不要使用 `latest`。

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

相机 RAW/JPG → NAS → 客户中文选片（选为精修）→ 项目资料目录内的 `PixCakeDelivery/03_SELECTED_RAW` → Photoshop / Lightroom / 像素蛋糕等修图软件 → `PixCakeDelivery/04_FINAL` → 自动替换客户页面上的原照片。

客户在 PicPeak 照片上能看到“原始预览 / 已选待精修 / 精修中 / 精修完成 V1、V2”等状态；开始精修后追加的照片会标出“后续追加”。客户可以对已交付版本提交带版本号的“返修申请”，也可以提交“新增需求 / 另做一个版本”；摄影师在 PicPeak 项目概览中查看需求、更新状态并回复。额外照片仍通过“选为精修”加入队列。

Bridge 按 `source_filename` 匹配原片，等待成片稳定后计算 SHA-256；同名返修再次同步，保留原 photo_id、评论、评分、选片和分享链接。默认保留最近 3 个成片版本。SELECTING 阶段取消可清理待精修副本，EDITING 后取消仅标记，支持后续追加。原片始终只读。RAW 支持 ARW/CR3/CR2/NEF/RAF/DNG/ORF/RW2；第一版成片支持 JPG/JPEG/PNG，默认单文件 100 MiB，要求文件 stem 唯一一致。

## 一体化结构

- PicPeak 页面：容器端口 3000，内置前端和后端，默认 SQLite；这是唯一对局域网开放的应用入口。
- Bridge：容器内 8080 端口，仅供 PicPeak 后端访问；没有宿主机端口映射，也没有独立登录页面入口。
- 容器内通过 `127.0.0.1` 通信，PicPeak 后端使用 Public API Token；Bridge 管理密码只用于内部接口鉴权，不需要摄影师登录 Bridge。
- `/data` 保存 PicPeak 数据、媒体、JWT 密钥和备份；`/bridge-data` 保存 Bridge SQLite。
- Supervisor 分别监控两个进程；进程异常自动重启，Docker 健康检查覆盖已启用的两个服务。
- 开启同步后，一个服务故障会让整个容器显示 unhealthy。Docker 的 restart 策略不会因 unhealthy 自动重启；应查日志处理，不能把健康检查当作自动修复。
- 两个服务升级、容器重启时会同时短暂中断。

## 通用 Docker 部署

### 1. 准备目录与单项目写入挂载

以 PicPeak 项目引用的 `Camera/26-10-04` 为例，照片与精修文件统一放在该项目资料目录下：

```text
Camera/26-10-04/
  01_RAW/
  02_PROOF/
  PixCakeDelivery/
    03_SELECTED_RAW/
    04_FINAL/
    05_HISTORY/
```

PicPeak 和 Bridge 对整个 Camera 根目录只读挂载；PicPeak 可从中选择 Proof 文件夹，Bridge 按项目引用的 RAW 子目录匹配原片。每个项目只把自己的 `PixCakeDelivery` 子目录单独挂载为可写，Camera/RAW 与其他项目仍为只读。由于挂载本身已经对应一个项目，Bridge 会直接在其中建立 `03_SELECTED_RAW`、`04_FINAL` 和 `05_HISTORY`，不再重复创建项目名子目录。升级时会把旧版 `event-编号-项目名` 目录下的阶段文件夹迁到挂载根目录；遇到新旧目录同时有文件时会停止迁移并报错，不会覆盖文件。Bridge 以 `BRIDGE_UID`/`BRIDGE_GID` 运行，需有权限读取 Camera、写入项目专属交付目录；摄影师账号需能读取待精修目录并写入成片目录。镜像只调整 Bridge 数据卷权限，不会自动修改照片目录权限。

先在 NAS 文件管理器中创建 `Camera/26-10-04/PixCakeDelivery`，然后设置 `.env` 的 `NAS_CAMERA_ROOT`、`NAS_PROJECT_5_DELIVERY_ROOT` 和 `PROJECT_DELIVERY_MOUNTS`。示例按 PicPeak 项目编号 5 和目录 `26-10-04` 配置；如编号或路径不同，请换成实际值。旧的 `/delivery` 挂载保留以兼容持久化的 Bridge 状态；新项目 5 的 PixCakeDelivery 单独挂载到 `/delivery-5`。Camera 继续只读。

每增加一个项目，都要在它引用的资料目录下创建 `PixCakeDelivery`，在 Compose 中增加这个项目专属的 bind mount（可映射到独立容器路径，例如 `/deliveries/9`），并在 `PROJECT_DELIVERY_MOUNTS` 加上项目编号、容器路径和宿主机路径。重启容器后，PicPeak 项目概览会检查挂载：检测到匹配路径时显示“自动关联项目文件夹”；未检测到时会提示更新 Compose。Docker 的挂载由容器启动时确定，网页不能替 Docker 修改宿主机挂载。

### 2. 构建或导入镜像

源码放在同一父目录，分别为 `picpeak-zh` 和 `pixcake-bridge`。获取中文 Fork `feat/zh-cn`，然后在 Bridge 仓库运行：

```sh
./docker/integrated/build.sh
```

默认构建 linux/amd64（适用于 x86 NAS 或服务器）；ARM NAS 构建时设置 `PLATFORM=linux/arm64`，应另行验收。构建先使用 PicPeak 自己的 Dockerfile，再组合 Bridge。独立执行 Compose build 前必须先构建固定版本 PicPeak 基础镜像。

离线导入：

```sh
docker save -o picpeak-pixcake-amd64.tar picpeak-pixcake:3.134.1-zh.19-bridge.0.1.7
```

在 NAS 容器管理界面导入 tar 并创建 Compose 项目；普通 Docker 主机可执行 `docker load -i picpeak-pixcake-amd64.tar`。此导入操作不需要重新构建镜像。

NAS 无法直接访问镜像仓库时，可运行 GitHub Actions 的 `Integrated image` 工作流并选择发布；成功后会附带 7 天有效的 NAS 导入 tar。导入后在 Compose 配置中使用对应固定版本标签，不要删除 PicPeak 或 Bridge 数据卷。

### 3. 首次初始化

复制 `.env.example` 为 `.env`，设置 `LAN_BIND_IP` 为 NAS 内网 IP、`NAS_CAMERA_ROOT` 为现有 Camera 绝对路径、`NAS_DELIVERY_ROOT` 为当前 PicPeak 项目资料目录中的 `PixCakeDelivery`，并设置至少 12 位的 `BRIDGE_ADMIN_PASSWORD`。初次保留 `BRIDGE_ENABLED=false`、`PICPEAK_TOKEN` 为空。不要把整个 Camera 根目录挂载为可写。

```sh
cp projects.example.json projects.json
docker compose up -d
```

访问 `http://NAS内网IP:3000`，按 PicPeak 初始化向导创建用户名管理员。初次部署的设置令牌保存在持久化 PicPeak 数据中，也可查看 PicPeak 启动日志。此时 Bridge 尚未监听端口，容器健康检查只检查 PicPeak。

完成后，在 PicPeak 设置中创建具有 read/write 权限的 Public API Token；填入 `.env` 的 `PICPEAK_TOKEN`，设置 `BRIDGE_ENABLED=true`。

```sh
docker compose up -d --force-recreate
```

在 PicPeak 后台打开目标项目的“概览”，使用“选片与精修进度”卡片。Compose 已为该项目单独挂载匹配的 PixCakeDelivery 时，可点击“自动关联项目文件夹”；Bridge 会验证 API Token、RAW 路径与挂载，再创建 `03_SELECTED_RAW`、`04_FINAL`、`05_HISTORY`。若未检测到挂载，按页面提示更新 Compose 并重启。绑定、阶段管理、照片状态、返修/新增需求、回复、立即同步、重新扫描和失败任务重试都在 PicPeak 完成，Bridge 不需要直接访问或登录。结果未知的上传任务需要先在 PicPeak 检查成片是否已替换，再确认重试。

### 4. 关联 NAS 照片

新建或管理项目时选择“关联 NAS 文件夹”，用 External Media Reference Mode 引用 `/external-media/项目名`。PROOF 挂载只读。引用其他已有照片文件夹时，将 `NAS_CAMERA_ROOT` 设置为该目录的真实绝对路径并使用下面的覆盖文件；文件名中的 nas-camera 是历史名称，适用于其他平台文件夹：

```sh
docker compose -f compose.yaml -f compose.nas-camera.yaml up -d
```

PicPeak「新建项目 / 管理项目 → 关联 NAS 照片文件夹」中，从 `/external-media/Camera` 选择该项目的 Proof 文件夹，避免把全部 Camera 导入同一项目。项目概览卡片填写相对于 Camera 根目录的 RAW 子目录；该目录应包含所选 Proof 对应的原片。Camera 已由主 Compose 只读挂载给 PicPeak 与 Bridge。

### 5. 使用任意基于文件夹的修图工作流

通过 SMB 或本地挂载，在修图电脑上访问 `NAS_CAMERA_ROOT/<项目资料目录>/PixCakeDelivery/03_SELECTED_RAW` 和同一目录下的 `04_FINAL`。电脑中的路径与容器中的路径可以不同，只要指向同一批实际文件。

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

项目资料路径可在 PicPeak 关联 NAS 文件夹时选择；Bridge 的 RAW 子目录应对应同一项目资料。PicPeak 与 Bridge 对 Camera 根只读；Bridge 仅写入每个项目单独挂载的 `PixCakeDelivery`。目录权限只允许所有者访问时，可叠加 `compose.nas-camera.yaml` 调整 PicPeak 的读取 UID。新项目需按上文增加专属挂载并重启，再在概览卡片自动关联。

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

NAS 配置文件权限：集成 Compose 首次启动时将空的只读示例 `projects.json` 复制到 Bridge 数据卷；PicPeak 项目概览中绑定项目后，配置写入持久化卷，重启不会覆盖。Camera 只读挂载用于相册引用和 RAW 匹配。

Camera 目录权限：若目录仅所有者可读，使用 `compose.nas-camera.yaml` 并将 `NAS_CAMERA_UID` 设置为 Camera 的实际所有者 UID（飞牛常见值为 1000，以实际检查为准）。此覆盖配置仅调整容器内 PicPeak 的运行身份，Camera 仍只读，保留源目录权限。应用后重建容器，再展开 Camera 验证。
