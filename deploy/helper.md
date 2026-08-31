# 服务器 Docker 运维速查

> 适用环境：阿里云 ECS · 复用 `wp_postgres` / `wp_redis` · `deploy/compose.app.yml`（API/Worker/Nginx 为 host 网络）  
> 代码目录：`/work_place/dating-backend` · Admin：`/work_place/dating-admin-web`  
> 环境变量：`/work_place/dating-backend/.env`（**勿提交 git**）

---

## 0. 前置约定

```bash
cd /work_place/dating-backend
export COMPOSE="docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env"
```

下文命令均默认已 `cd` 到 `dating-backend` 目录。

**不要动这些：**

- `wp_postgres`、`wp_redis` 容器及其数据卷
- 对 infra / `wp_*` 执行 `docker compose down -v`

---

## 1. 日常更新代码（最常用）

```bash
cd /work_place/dating-backend
git pull

# 若改了运营后台且未进 git，本机执行：
# scp -r dating-admin-web/* root@<IP>:/work_place/dating-admin-web/

docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build
```

等待约 30～60 秒（构建 + Alembic + 健康检查），然后验收：

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1/health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

**说明：** API 启动命令里已包含 `alembic upgrade head`，一般**无需单独跑迁移**。

---

## 2. 只重建某一个服务

```bash
# 只更 API + Worker（后端 Python 改动）
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build api worker

# 只更运营后台
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build admin

# 只重载 Nginx 配置（改了 deploy/nginx/dating.conf）
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d nginx
```

---

## 3. 数据库迁移（Alembic）

### 自动（推荐）

每次 `api` 容器启动时执行：

```text
alembic upgrade head && uvicorn ...
```

更新代码后 `up -d --build` 即可。

### 手动（排障 / 确认版本）

```bash
# 查看当前迁移版本
docker exec dating-api alembic current

# 查看待执行迁移
docker exec dating-api alembic heads

# 手动升级到最新（api 需在运行）
docker exec dating-api alembic upgrade head

# 回滚一步（谨慎，生产慎用）
docker exec dating-api alembic downgrade -1
```

### 迁移前备份（有大表结构变更时建议）

```bash
bash deploy/scripts/backup-pg.sh
# 或手动：
docker exec wp_postgres pg_dump -U app -d app -Fc \
  > /opt/dating/backups/app-$(date +%Y%m%d-%H%M%S).dump
```

---

## 4. 备份与恢复

### 备份

```bash
mkdir -p /opt/dating/backups
bash deploy/scripts/backup-pg.sh
ls -lh /opt/dating/backups/
```

### 恢复到 `app` 库（会覆盖，慎用）

```bash
# 先停写流量的 api
docker stop dating-api dating-worker

docker exec -i wp_postgres pg_restore -U app -d app --clean --if-exists \
  < /opt/dating/backups/你的备份文件.dump

docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d api worker
```

---

## 5. 查看状态与日志

```bash
# 容器状态
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 健康检查
curl -sS http://127.0.0.1:8000/health | python3 -m json.tool
curl -sS http://127.0.0.1/health

# 最近日志
docker logs dating-api --tail 100 -f
docker logs dating-worker --tail 50
docker logs dating-nginx --tail 50
docker logs dating-admin --tail 50

# 旧库日志（一般不用动）
docker logs wp_postgres --tail 30
docker logs wp_redis --tail 30
```

---

## 6. 启停与重启

```bash
# 停应用栈（不动 wp_postgres / wp_redis）
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env down

# 启动
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d

# 重启单个容器
docker restart dating-api
docker restart dating-nginx
```

---

## 7. 环境变量

```bash
# 编辑（改 JWT、OSS、Admin 密码等）
nano /work_place/dating-backend/.env
chmod 600 /work_place/dating-backend/.env

# 改 .env 后需重建受影响容器
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --force-recreate api worker
```

**云上关键项（复用 wp 库 + host 网络）：**

```env
POSTGRES_HOST=127.0.0.1
POSTGRES_USER=app
POSTGRES_PASSWORD=app
POSTGRES_DB=app
REDIS_URL=redis://127.0.0.1:6379/0

NGINX_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine
PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
NODE_IMAGE=docker.m.daocloud.io/library/node:20-alpine
```

---

## 8. 探活与连通性

```bash
# 宿主机 API
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/docs

# 经 Nginx（对外入口）
curl -sS http://127.0.0.1/health
curl -sI http://127.0.0.1/

# Admin 静态（仅本机）
curl -sI http://127.0.0.1:8081/

# 数据库
docker exec wp_postgres psql -U app -d app -c 'select 1'

# Redis（宿主机无 redis-cli 时）
docker exec wp_redis redis-cli ping
```

---

## 9. 镜像与构建

```bash
# 预拉基础镜像（Docker Hub 不通时用 DaoCloud）
docker pull docker.m.daocloud.io/library/python:3.12-slim
docker pull docker.m.daocloud.io/library/nginx:1.27-alpine
docker pull docker.m.daocloud.io/library/node:20-alpine

# 无缓存全量重建 API
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env build --no-cache api worker
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d

# 查看本地镜像
docker images | grep -E 'dating-|nginx|python'
```

---

## 10. 常见问题速查

| 现象 | 处理 |
|------|------|
| `502` on `:80`，`:8000/health` 正常 | 检查 `deploy/nginx/dating.conf` 是否指向 `127.0.0.1:8000`；`nginx` 是否为 `network_mode: host` |
| API 一直 `restarting` | `docker logs dating-api --tail 80`；查 `.env` 里 `POSTGRES_*` / `REDIS_URL` |
| `password authentication failed` | `.env` 中 `POSTGRES_PASSWORD` 须与 `wp_postgres` 一致（当前为 `app`） |
| `Connect call failed` 容器间连库 | 本机方案已用 **host 网络 + 127.0.0.1**，勿改回 `wp_postgres` 容器名 |
| `compose.yml: Additional property api` | YAML 结构损坏，用仓库中 `deploy/compose.app.yml` 整文件覆盖 |
| `Couldn't find env file: /opt/dating/.env` | 使用 `--env-file ./.env`；删除 `.env` 里错误的 `ENV_FILE=/opt/dating/.env` 行 |
| 拉镜像超时 | `.env` 配置 `*_IMAGE=docker.m.daocloud.io/library/...` |
| 80 端口被占 | `ss -lntp \| grep :80`；停冲突服务或改 `dating.conf` 的 `listen` |

---

## 11. 端口一览

| 地址 | 用途 |
|------|------|
| `http://<公网IP>/` | 运营后台（Nginx → Admin） |
| `http://<公网IP>/health` | 健康检查 |
| `http://<公网IP>/api/v1/...` | 客户端 API |
| `http://<公网IP>/docs` | Swagger |
| `127.0.0.1:8000` | API 直连（仅服务器本机） |
| `127.0.0.1:8081` | Admin 静态（仅服务器本机） |
| `127.0.0.1:5432` / `6379` | wp 库/缓存（勿对公网开放） |

Android `API_BASE_URL`：`http://<公网IP>/`

---

## 12. 一键脚本（仓库内）

```bash
# 首次部署（新建库时；复用 wp 见 DEPLOYMENT_SETUP.md）
bash deploy/scripts/first-up.sh --reuse-infra --postgres wp_postgres --redis wp_redis

# 日常只更应用
bash deploy/scripts/update-app.sh   # 需 ENV：服务器上建议直接用第 1 节 compose 命令

# 备份
bash deploy/scripts/backup-pg.sh

# 探活旧库
bash deploy/scripts/probe-infra.sh
```

> 当前阿里云环境已固定为 **host 网络版** `compose.app.yml`，日常以 **第 1 节** 命令为准。

---

## 13. 相关文档

- [DEPLOYMENT_SETUP.md](../../DEPLOYMENT_SETUP.md) — 完整搭建方案
- [deploy/.env.example](./.env.example) — 环境变量模板
- [README.md](../README.md) — 后端 API 说明
