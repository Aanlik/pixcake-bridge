# PixCake Bridge · 飞牛 NAS 中文选片与精修交付

独立 Python 3.12 / FastAPI 服务，通过 PicPeak Public API Token 轮询客户选片，
生成待精修 RAW，并将像素蛋糕导出的成片替换回原画廊。像素蛋糕无需 API。
PicPeak 中文 Fork 保留官方 stable 历史，Bridge 的摄影业务自动化不进入 PicPeak。

当前版本：Bridge `0.1.0`，PicPeak `3.134.1-zh.3`。
这是可构建、可运行的第一版；实际 fnOS、FN Connect 和像素蛋糕验收仍需设备。
测试证据见 [测试计划](docs/testing.md) 和 [验证报告](docs/verification.md)。

## 工作流程

```text
01_RAW（原始照片，只读） + 02_PROOF（JPG，只读）
 → PicPeak 客户中文选片，绿色=精修
 → Bridge 生成 03_SELECTED_RAW
 → 像素蛋糕读取 RAW，导出同 stem 的 JPG 到 04_FINAL
 → Bridge 等待文件稳定、SHA256 去重、记录版本到 05_HISTORY
 → replaces_photo_id 替换原 Proof，原 photo_id/反馈/分享链接保留
```

RAW 支持 ARW、CR3、CR2、NEF、RAF、DNG、ORF、RW2，扩展名不区分大小写。
FINAL 第一版支持 JPG/JPEG/PNG，单文件默认上限 100 MiB。
RAW/FINAL 必须按 `source_filename` 的 stem 唯一匹配：
`DSC00125.JPG` → `DSC00125.ARW` → `DSC00125.JPG`。
多相机重名、多扩展名同 stem、重复 Proof 均作为冲突停止该照片，不随意选一个。

## 推荐部署：PicPeak AIO

单摄影师/NAS 优先使用官方 AIO 结构：一个 Node 服务、SQLite、内置前端，
无需另外部署 nginx/PostgreSQL/Redis。PicPeak 数据在 `/data`，Bridge 使用自己的
SQLite；两者在同一 Docker 网络中通过 `http://picpeak:3000` 通信。
需要迁移 PostgreSQL 时，PicPeak 可配置 `DATABASE_CLIENT=pg` 及 DB_*；Bridge
使用 SQLAlchemy，提供 `postgres` 可选依赖，迁移说明见下文。

## 飞牛 fnOS 部署

### 1. 准备项目目录与权限

在飞牛文件管理器建立：

```text
摄影项目/示例项目/
  01_RAW/
  02_PROOF/
  03_SELECTED_RAW/
  04_FINAL/
  05_HISTORY/
```

上传相机 RAW 到 `01_RAW`，用于客户选片的 JPG 到 `02_PROOF`。
请从 fnOS 查看真实绝对路径，例如 `/vol1/1000/摄影项目/示例项目`；示例路径
不能照抄假定是您的设备路径。

Bridge 默认 UID/GID 1001。通过 fnOS 权限界面或管理员终端，让该身份能读取
RAW/FINAL、写入 SELECTED/HISTORY；摄影师的 SMB 账号能读取 SELECTED、写入 FINAL。
不要将整个摄影项目可写挂载给 Bridge。`compose.yaml` 已把 RAW、PROOF 和 FINAL
分别只读挂载。若 fnOS 用户组不同，可给 Bridge 添加该共享目录的补充组：

```yaml
# compose.override.yaml，仅在确有需要时配置真实 NAS 用户组 ID
services:
  bridge:
    group_add: ["1000"]
```

RAW 原始文件可保持摄影师现有权限。默认 auto 模式只有原始 inode 没有写权限
时才尝试 hardlink；否则自动改用 reflink/copy，避免后期软件通过硬链接写坏原片。
Bridge 不会 chmod 原片。同盘的两个独立 bind mount 也可能产生 EXDEV，因此即使
同文件系统也可能回退。若无法保证后期软件只读 RAW，请设置 `RAW_MATERIALIZE_MODE=copy`。
待精修副本生成后为只读。root 或管理员仍能修改硬链接 inode；需要强隔离时必须 copy。

### 2. 放置两个独立仓库

```text
部署目录/
  picpeak-zh/
  pixcake-bridge/
```

```bash
git clone --branch zh-stable https://github.com/Aanlik/picpeak-zh.git
git clone https://github.com/Aanlik/pixcake-bridge.git
cd pixcake-bridge
cp .env.example .env
cp projects.example.json projects.json
```

Bridge 仓库默认私有，克隆需要您的 GitHub 身份；也可直接使用本次生成的本地目录。
在飞牛 Docker 应用中创建 Compose 项目，选择 `pixcake-bridge/compose.yaml`。
项目配置要包含 `.env` 和 `projects.json`。

### 3. 编辑环境变量并构建

填写 `.env`：

* `PHOTO_PROJECT`：完整摄影项目路径；`PROJECT_FOLDER`：项目目录名称。
* `LAN_BIND_IP`：NAS 的局域网 IP，例如 `192.168.1.50`；默认 127.0.0.1 仅本机。
* `BRIDGE_ADMIN_PASSWORD`：随机、至少 12 位的管理密码。
* `PICPEAK_IMAGE`/`BRIDGE_IMAGE`：保持明确版本；正式发布可换成镜像 digest。
* `PICPEAK_TOKEN` 暂保留占位值，完成下一步后替换。

```bash
docker compose build
docker compose up -d picpeak
```

Compose 不会静默创建不存在的 NAS 目录；缺目录会直接报错。默认部署支持一个项目。
多个项目需在 `projects.json` 逐个添加 event_id/路径，同时增加每个项目的四个独立
Bridge 挂载和 PicPeak PROOF 挂载；禁止用一个可写 NAS 总目录替代。

### 4. 初始化 PicPeak、设置中文、创建 Public API Token

打开 `http://NAS局域网IP:3000/admin`，读取初始化令牌：

```bash
docker compose exec picpeak cat /data/db/SETUP_TOKEN
```

按中文向导创建管理员账号。进入“设置 → 常规 → 默认语言”选择“简体中文”。
**必须保存此设置**：画廊登录页采用官方 `general_default_language` 设置，单独
设置 Docker 的 `PICPEAK_DEFAULT_LANGUAGE` 不能替代后台默认语言。
前端构建参数决定初始化默认；访客之后可切换语言，摄影师后台也可选择中文。

在后台集成/API 令牌页创建专用令牌，scope 仅 `read` + `write`。
账号角色需要 `events.view`、`photos.view`、`photos.upload` 及目标项目访问权。
不授予 Bridge `admin` scope，不填写管理员账号密码。保存一次性显示的 `pp_live_…`
到 `.env` 的 `PICPEAK_TOKEN`；不要把 `.env` 提交到 Git。

### 5. 建立外部引用画廊

在 PicPeak 创建摄影项目，选择 External Media Reference Mode，导入
`/external-media/示例项目`（对应 NAS 的 `02_PROOF`）。缩略图写入 PicPeak `/data`，
原 Proof 只读。官方外部目录监视器与周期扫描可发现后续新增 Proof。

开启反馈和颜色标记，建议按客户身份保存；中文绿色显示为“选为精修/已选精修”。
多人选片时，Bridge 默认采用官方 `mark_source=client` 合并后的颜色，**不是**
任意一位客户点绿就一定选中；业务应使用单一客户或共享颜色模式取得统一结果。
共享模式中任何客户都能改颜色，需先与客户约定。

从画廊管理页/API 得到数字 event_id，填入 `projects.json`。
其中四个容器路径必须与 Compose 挂载一致。编辑配置后重启 Bridge。

```bash
# 本机有 Python/uv 时运行；不输出令牌内容
python3 scripts/preflight.py
docker compose up -d bridge
docker compose ps
```

Bridge 管理入口 `http://NAS局域网IP:8080`，账号 `admin`，密码为配置值。
后台显示客户已选、RAW 匹配、待精修、已精修、已同步、返修、取消待确认与异常。
提供手动同步、重新扫描、重试、推进项目阶段。
**禁止通过 FN Connect、反向代理或公网转发 Bridge 端口**；客户只访问 PicPeak。
生产建议为管理访问配置局域网 HTTPS。

### 6. 像素蛋糕

像素蛋糕通过本机/SMB 读取 `03_SELECTED_RAW`，输出固定为 `04_FINAL`。
保持相机 stem，例如 `DSC00125.ARW → DSC00125.JPG`，禁用随机命名/自动序号后缀。
Bridge 使用文件事件加周期扫描，连续至少 STABLE_SECONDS 秒未变才创建上传快照。
再次导出同名文件且 SHA256 变化时自动作为返修上传。

像素蛋糕已打开的项目能否自动发现新增 RAW，当前无实机证据。若不能自动发现，
使用“刷新/重新导入目录”操作。Bridge 不调用像素蛋糕 API，不依赖此自动发现能力。

## 阶段与取消行为

| 阶段 | 客户新增 | 客户取消 | FINAL |
|---|---|---|---|
| SELECTING | 自动生成 RAW | 删除经哈希核对的 Bridge 副本 | 稳定后可同步 |
| EDITING | 继续追加 RAW | 标记取消，保留正在精修的 RAW | 自动同步 |
| DELIVERED | 继续追加 RAW | 保留 RAW，摄影师处理 | 允许返修 |
| ARCHIVED | 停止轮询 | 不处理 | 停止上传 |

阶段只能前进，不允许从 EDITING 退回 SELECTING，以免意外删除在修文件。
取消后已经上传的成片不会自动撤回。归档为 Bridge 同步状态，与 PicPeak 的画廊
归档分别控制；完成项目后应在两端按需要归档。

## 持久化、版本和故障恢复

SQLite 保存 projects/photos/deliveries/sync_runs/errors，启用 WAL/外键/忙等待。
Bridge 单进程运行，定时和手动任务共用锁，不能启动多个副本或多个 uvicorn worker。
哈希相同的当前 FINAL 跳过；返修新哈希替换同一个 photo_id。
`05_HISTORY/<photo_id>/` 保留最近 3 个成功版本，任务摘要留在数据库。
上传中的/失败的版本不会为了满足 3 个版本而被删除，以便诊断与重试。

为恢复“服务器成功但响应丢失”，上传文件名保留相机 stem 并附加 `.__bridge_<sha256>`
标记。官方 API 能读取该 original_filename，重启后据此确认结果；source_filename
仍保持相机原名。客户端显示/下载名可能包含标记，这是第一版已知限制。
没有上游幂等键时无法从理论上保证所有网络故障下的 exactly-once：仍无法确认的
任务进入 UNKNOWN，自动暂停；摄影师先核对 PicPeak，再从后台重试。
401/403/404 和确定失败记录异常；429 延后下一周期重试；5xx/中断的上传结果进入核对。
GET 请求短暂失败最多重试 3 次，API 故障不会当作“全员取消”。

同一 Proof 重复导入不会把精修重新覆盖为原片：官方 external_relpath 去重保留
已替换记录，替换后媒体转为 managed。最终上传文件也储存在 NAS 的 PicPeak `/data`；
需要为 FINAL、3 个历史版本与 PicPeak 成片副本预留存储。

## FN Connect：先验收匿名分享，再开放客户入口

目前尚未提供 NAS 实例，无法完成现场 Spike。请按 [FN Connect 验收单](docs/fn-connect-spike.md)
在未登录飞牛账号的外部手机上测试真实 PicPeak 分享链接；飞牛“文件外链分享”
可用不能证明任意 Docker 网页应用都可匿名访问。验收未通过前不要向客户承诺远程可用。
内部网络、目录、Bridge 地址不受公网入口选择影响。

若不支持匿名应用转发，备选为自有域名 + VPS HTTPS 反向代理 + FRP/SSH 反向隧道，
仅转发 PicPeak；需要自行评估服务器费用、照片带宽与维护。摄影师异地 RAW 可用
Tailscale + SMB，客户无需接触 RAW 或 Bridge。

## 本地开发与测试

```bash
uv sync --python 3.12 --extra test
uv run pytest -q
uv run uvicorn pixcake_bridge.app:app --host 127.0.0.1 --port 8080
```

本地启动需配置环境中的 PROJECTS_FILE、PICPEAK_URL、PICPEAK_TOKEN、DATABASE_URL、
BRIDGE_ADMIN_PASSWORD。production Compose 的路径是容器路径，不能直接用于本机启动。

真实集成测试需要专用 PicPeak 测试容器、全新的数据卷/本地 fixture 目录，参考
[测试文档](docs/testing.md)。`scripts/integration.py` 从真实客户反馈接口选片，
用 read/write token 调用替换接口，校验 ID、评论、评分、选择、名称排序、分享链接、
最终文件哈希、RAW 不变与重启后无重复上传。不要对生产实例运行该脚本。

## 备份、升级与 PostgreSQL 迁移路径

停止 Bridge 后备份其命名数据卷中的整个 `/data`，不要只复制 bridge.db 而遗漏 WAL。
PicPeak 使用内置一致性备份或停机备份 `/data`；摄影项目单独备份。
更新镜像前记录 digest，执行上游维护流程：
[中文 Fork 维护文档](../picpeak-zh/docs/zh-CN-maintenance.md)。
更新后验收健康状态、一轮选片同步和一张返修，再恢复日常使用。

Bridge 初始模型与数据库连接不绑定 SQLite，迁移 PostgreSQL 时安装
`uv sync --extra postgres`，设置 `DATABASE_URL=postgresql+psycopg://…`。
先停机、建立同结构数据库、按 projects → photos → deliveries/sync_runs/errors 顺序
导入并保留主键，修正 PostgreSQL sequence，验证外键/行数/哈希后切换。
生产 Dockerfile 默认未安装 PostgreSQL extra；需要构建带该依赖的新版本。
此迁移路径已预留，**没有宣称跨数据库迁移已实际测试**。未来字段变更应引入显式
版本化迁移；当前 create_all 不会自动升级已有字段。

## 已知限制

详见 [风险与限制](docs/risks.md)。尤其注意：真实手机/微信、FN Connect、像素蛋糕
与 NAS 断电尚需现场验收；专业长尾文案属于机器辅助初译；原始 hardlink inode 需要
额外权限保证；上游替换会更新拍摄 EXIF，按拍摄时间排序时需像素蛋糕保留原 EXIF。
本项目不会伪造这些现场验证结果。

### 本地账号与链接分享

当前中文 AIO 使用用户名登录，客户选片不填邮箱，发布后复制链接自行交付给客户；SMTP 与邮件入口关闭。本地管理员在后台创建，初始密码私下交付。邮件依赖的门户与合同交付模块不启用，未提供短信/微信自动发送。详情见同级 PicPeak `docs/zh-CN-no-email.md`。
