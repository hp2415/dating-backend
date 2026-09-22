# dating-backend 操作手册

Git：https://github.com/hp2415/dating-backend.git  
协作：[AGENTS.md](../AGENTS.md) · 工作区：[../../AGENTS.md](../../AGENTS.md)  
云上命令速查：[deploy/helper.md](../deploy/helper.md)

## 1. 它做什么

给找搭子 App 和运营后台提供 API。

| 入口 | 用途 |
|------|------|
| `http://localhost:8000/docs` | Swagger |
| `http://localhost:8000/health` | 健康检查 |
| `/api/v1/*` | iOS / Android |
| `/admin/v1/*` | `dating-web` 运营后台 |

## 2. 本机启动

需要 Docker Desktop、仓库根目录 `.env`（从 `.env.example` 复制）。

```powershell
cd d:\Android\dating-backend
copy .env.example .env
docker compose up -d --build
```

服务：API `:8000` · Postgres `:5432` · Redis `:6379` · MinIO `:19000`（控制台 `:19010`）。

Compose 里的 `admin` 服务会构建 **上一级的 `dating-web`**。若本地目录名不是这个，见 [dating-web/docs/OPS.md](../../dating-web/docs/OPS.md)。

停止应用栈（开发库可删卷；**生产禁止** `-v`）：

```powershell
docker compose down
```

## 3. 常用验收

开发登录：手机号 + 密码（`scripts/create_app_account.py`）。本地 `APP_ENV=development` 仍可用短信码 `123456`。运营账号 `admin` / `Admin@123456`。

```powershell
.\scripts\smoke_test.ps1
.\scripts\smoke_m2.ps1
.\scripts\smoke_activity.ps1
.\scripts\smoke_moderation.ps1
.\scripts\smoke_community.ps1
```

迁移：API 容器启动时执行 `alembic upgrade head`。新版本文件放在 `alembic/versions/`。

## 4. 服务器发版（git pull）

约定：

| 项 | 值 |
|----|-----|
| 代码 | `/work_place/dating-backend` |
| 运营前端 | `/work_place/dating-admin-web`（对应本机 `dating-web`） |
| 环境变量 | `/work_place/dating-backend/.env`（chmod 600，不进 git） |
| Compose | `deploy/compose.app.yml`，项目名 `dating-app` |
| 复用 | 已有 `wp_postgres` / `wp_redis`，**不要 down -v** |

日常更新：

```bash
cd /work_place/dating-backend
git pull origin master

cd /work_place/dating-admin-web
git pull origin main

cd /work_place/dating-backend
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build
```

等 30～60 秒后：

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1/health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

只更 Python：

```bash
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build api worker
```

只更运营后台：

```bash
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build admin
```

对外入口（Nginx `:80`）：

| 路径 | 去向 |
|------|------|
| `/` | 运营后台静态资源 |
| `/api/` `/admin/` `/docs` `/health` | FastAPI |

Android / iOS 的生产 `API_BASE_URL` 用 `http://<公网IP>/`（末尾斜杠与客户端实现保持一致）。

排障、备份、端口表见 [deploy/helper.md](../deploy/helper.md)。

## 5. 和别的仓怎么连

- 新客户端字段：先在本仓 schema + 迁移，再改 Android / iOS。
- 新审核动作：同时改 `dating-web` 审核页。
- 活动默认待审，运营 `POST /admin/v1/activities/{id}/review` 后才公开。
