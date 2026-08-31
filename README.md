# Dating Backend

FastAPI modular monolith for the enterprise dating app (M1: auth + profile + media).

## Stack

- Python 3.12 + FastAPI
- PostgreSQL 16 + Redis 7
- Alembic migrations
- MinIO (local OSS)
- JWT access/refresh tokens

## Quick start

```bash
cd dating-backend
cp .env.example .env
docker compose up -d --build
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

拆分部署（infra 与 app 分开，云上发版只更新 app）见 [`deploy/`](./deploy/)（含 [运维速查 deploy/helper.md](./deploy/helper.md)）与仓库根目录 [`DEPLOYMENT_SETUP.md`](../DEPLOYMENT_SETUP.md)。

Migrations run automatically on API container start (`alembic upgrade head`).

## Implemented APIs (M1)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/sms/send` | No | Send SMS code (dev returns `dev_code`) |
| POST | `/api/v1/auth/sms/login` | No | Login/register, returns tokens |
| POST | `/api/v1/auth/token/refresh` | No | Rotate refresh token |
| POST | `/api/v1/auth/logout` | No | Revoke refresh token |
| GET | `/api/v1/me` | Bearer | Current user + profile |
| PUT | `/api/v1/me/profile` | Bearer | Update profile |
| PUT | `/api/v1/me/preferences` | Bearer | Update match preferences |
| POST | `/api/v1/account/delete` | Bearer | Soft delete account |
| POST | `/api/v1/media/sts` | Bearer | Presigned upload URL |
| POST | `/api/v1/media/complete` | Bearer | Register uploaded object |

## Smoke test

```bash
# 1) send code
curl -s -X POST http://localhost:8000/api/v1/auth/sms/send ^
  -H "Content-Type: application/json" ^
  -d "{\"phone\":\"13800138000\"}"

# 2) login (dev code 123456)
curl -s -X POST http://localhost:8000/api/v1/auth/sms/login ^
  -H "Content-Type: application/json" ^
  -d "{\"phone\":\"13800138000\",\"code\":\"123456\",\"device_id\":\"dev-1\",\"platform\":\"android\"}"

# 3) update profile (replace TOKEN)
curl -s -X PUT http://localhost:8000/api/v1/me/profile ^
  -H "Authorization: Bearer TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"display_name\":\"林夏\",\"birthday\":\"1998-05-20\",\"gender\":\"female\",\"city\":\"上海\",\"bio\":\"hello\",\"tags\":[\"旅行\",\"咖啡\"]}"
```

## Project layout

```text
app/
  main.py
  models/           # SQLAlchemy entities
  modules/
    auth/
    user/
    media/
  shared/           # config, db, redis, security, deps
alembic/versions/   # migrations
workers/            # background worker placeholder
```

## M2 APIs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/discover/cards` | 推荐卡片（Redis 曝光去重） |
| POST | `/api/v1/swipes` | 喜欢/跳过（幂等键） |
| GET | `/api/v1/matches` | 匹配列表 |
| DELETE | `/api/v1/matches/{id}` | 取消匹配 |
| POST | `/api/v1/chat/token` | IM Token 门禁（当前 noop 预留） |

Demo users are seeded as `1990000xxxx` on startup.

```powershell
.\scripts\smoke_m2.ps1
```

## Safety / Moderation APIs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reports` | 举报（可选 `also_block`） |
| POST | `/api/v1/blocks` | 拉黑（级联 match→blocked） |
| GET | `/api/v1/blocks` | 拉黑列表 |
| DELETE | `/api/v1/blocks/{user_id}` | 解除拉黑 |
| GET | `/admin/v1/reports` | 举报工单列表 |
| POST | `/admin/v1/reports/{id}/resolve` | 处置：dismiss/warn/limit/ban |
| GET | `/admin/v1/media` | 媒体审核列表 |
| POST | `/admin/v1/media/{id}/review` | approve/reject |

```powershell
.\scripts\smoke_moderation.ps1
```

## Activity APIs（找搭子主链路）

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/activities` | 发起活动（待审；media 支持 media_id/URL） |
| GET | `/api/v1/activities` | 已发布信息流；`mine=hosted|joined` |
| GET | `/api/v1/activities/{id}` | 详情聚合（地址/图片/成员） |
| POST/DELETE | `/api/v1/activities/{id}/join` | 报名 / 退出 |
| POST/DELETE | `/api/v1/activities/{id}/like` | 感兴趣 |
| GET/POST | `/api/v1/activities/{id}/comments` | 活动动态评论 |
| GET | `/admin/v1/activities` | 活动审核队列 |
| POST | `/admin/v1/activities/{id}/review` | approve / reject |

OSS：`activity_image` / `activity_video` 已预留 STS；地图 SDK 仅存 lat/lng。社区帖子 API 保留兼容，产品入口已并入活动动态。

```powershell
.\scripts\smoke_activity.ps1
```

## Community APIs

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/community/posts` | 发帖（待审；media 支持 `media_id` 或 URL 占位） |
| GET | `/api/v1/community/posts` | 已发布信息流；`mine=true` 看自己的 |
| POST/DELETE | `/api/v1/community/posts/{id}/like` | 点赞 / 取消 |
| GET/POST | `/api/v1/community/posts/{id}/comments` | 评论列表 / 发表评论 |
| GET | `/admin/v1/community/posts` | 帖子审核队列 |
| POST | `/admin/v1/community/posts/{id}/review` | approve / reject |

OSS：`media_type=post_image|post_video` 已预留 STS；客户端可先填 URL。

```powershell
.\scripts\smoke_community.ps1
```

## Next (M3+)

- 第三方 IM SDK（RongCloud / NetEase）替换 `NoopImProvider`
- 推送深化、用户检索后台、配置中心
- 社区真上传与视频播放器

## Admin

- API: `/admin/v1/auth/login`, `/admin/v1/auth/me`, `/admin/v1/dashboard/summary`（真实计数）
- 审核：`/admin/v1/reports`、`/admin/v1/media`
- 默认账号：`admin` / `Admin@123456`（启动自动种子，无短信）
- 前端：`../dating-admin-web`，Compose 服务名 `admin`，端口 `5173`，页面「内容审核」
