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

开发登录：手机号 + 密码（`scripts/create_app_account.py`）。本地仍可用短信码 `123456`。运营种子账号：`admin`（超管）/ `auditor`（审核员）/ `finance`（财务），密码均为 `Admin@123456`（仅本地/演示种子）。演示内容：`python scripts/seed_content.py --base http://127.0.0.1:8000`（见 [DEMO_SEED.md](./DEMO_SEED.md)）。

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

### 演示环境核对

`compose up` **之前**在服务器 `/work_place/dating-backend/.env` 确认（勿提交真实密钥）：

| 变量 | 演示建议 | 说明 |
|------|----------|------|
| `SMS_ALLOW_DEV_CODE` | `true` | 内测固定短信码；staging/production 逻辑仍可能忽略，以代码为准 |
| `IM_PROVIDER` | `tencent` | 体验版 IM；本地可为 `noop` |
| `TENCENT_IM_SDK_APP_ID` | 控制台 SDKAppID | 与 `config.py` 字段 `tencent_im_sdk_app_id` 对应 |
| `TENCENT_IM_SECRET_KEY` | 控制台密钥 | 与 `tencent_im_secret_key` 对应 |
| `PAYMENT_STUB_AUTO_COMPLETE` | `true` | stub 通道即时完成 |
| `MEDIA_AUTO_APPROVE` | 按需 `true` | 媒体自动过审 |
| `SENTRY_DSN` | 可选 | 空则不上报 |

发版：**两仓都 `git pull`**，再：

```bash
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build
```

**禁止** `docker compose down -v`（会打到共用的 `wp_postgres` / `wp_redis`）。

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
curl -sS https://123.56.118.242/health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 公网 HTTPS（没有域名）

Let’s Encrypt 给公网 IP 签发证书，有效期约 6 天，必须自动续期。API 只监听 `127.0.0.1:8000`，外网只走 Nginx 的 443。`/docs` 在非 development 环境关闭。阿里云安全组放行 **80 和 443**。不要执行 `docker compose down -v`。

Certbot 用 Docker 跑，不在系统里装包。容器必须加 `--network host`，否则解析不了 `acme-v02.api.letsencrypt.org`。镜像入口已经是 `certbot`，命令从 `certonly` 开始。

在 `/work_place/dating-backend` 执行。

**1. 临时证书，让 Nginx 能启动**

```bash
mkdir -p /etc/letsencrypt/live/public-ip /var/www/certbot/.well-known/acme-challenge
cat > /tmp/ip-cert.cnf <<'EOF'
[req]
distinguished_name = req_dn
x509_extensions = v3_req
prompt = no
[req_dn]
CN = 123.56.118.242
[v3_req]
subjectAltName = IP:123.56.118.242
EOF
openssl req -x509 -nodes -newkey rsa:2048 -days 2 \
  -keyout /etc/letsencrypt/live/public-ip/privkey.pem \
  -out /etc/letsencrypt/live/public-ip/fullchain.pem \
  -config /tmp/ip-cert.cnf
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d
```

**2. 换成 Let’s Encrypt 证书**

```bash
docker pull docker.m.daocloud.io/certbot/certbot:latest
docker run --rm --network host \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot \
  docker.m.daocloud.io/certbot/certbot:latest \
  certonly --webroot -w /var/www/certbot \
  --preferred-profile shortlived \
  --ip-address 123.56.118.242 \
  --agree-tos --register-unsafely-without-email --non-interactive \
  --keep-until-expiring
rm -rf /etc/letsencrypt/live/public-ip
ln -sfn /etc/letsencrypt/live/123.56.118.242 /etc/letsencrypt/live/public-ip
docker exec dating-nginx nginx -t
docker exec dating-nginx nginx -s reload
curl -fsS https://123.56.118.242/health
```

宿主机先确认能解析：`getent hosts acme-v02.api.letsencrypt.org`。没有结果时，把 `/etc/resolv.conf` 的 nameserver 改成 `223.5.5.5` 后再跑第 2 步。

**3. 自动续期**（每天 03:17 和 15:17，未到期时 certbot 不会重新签发）

```bash
cat > /etc/cron.d/dating-certbot <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
17 3,15 * * * root docker run --rm --network host -v /etc/letsencrypt:/etc/letsencrypt -v /var/www/certbot:/var/www/certbot docker.m.daocloud.io/certbot/certbot:latest renew --quiet && docker exec dating-nginx nginx -s reload
EOF
chmod 644 /etc/cron.d/dating-certbot
```

仓库脚本 `deploy/scripts/enable-https-ip.sh` 做的是同一件事。可选 `CERTBOT_EMAIL=you@example.com`。

改密：登录运营后台，右上角账号菜单里「修改密码」。新密码至少 8 位。保存后需要重新登录。种子脚本若仍要登录后台，在服务器上先 `export ADMIN_DEFAULT_PASSWORD='新密码'`。

Android 正式包的接口地址改为 `https://123.56.118.242/`。证书生效后再打 release 包，旧的 HTTP 包会被 301 打断。

只更 Python：

```bash
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build api worker
```

只更运营后台：

```bash
docker compose -p dating-app -f deploy/compose.app.yml --env-file ./.env up -d --build admin
```

对外入口（Nginx `:443`，`:80` 只留给证书校验并跳转到 HTTPS）：

| 路径 | 去向 |
|------|------|
| `/` | 运营后台静态资源 |
| `/api/` `/admin/` `/health` | FastAPI |
| `/docs` `/redoc` `/openapi.json` | 关闭 |

Android / iOS 的生产 `API_BASE_URL` 用 `https://123.56.118.242/`（末尾斜杠与客户端实现保持一致）。

排障、备份、端口表见 [deploy/helper.md](../deploy/helper.md)。

日志留在容器标准输出里，每条请求一行（方法、路径、状态码、耗时、`request_id`）。`/health` 不记。服务器上是 JSON，本机 development 是普通文本。Nginx 把同一个 `request_id` 传给 API。每个容器最多保留 5 个 20MB 文件。业务流水仍在库里：`admin_audit_logs`、`sms_send_logs`、`analytics_events`。不在这台机器上再跑一套 Loki 或 Elasticsearch。以后要按天检索，把这四份标准输出接到阿里云日志服务即可，格式不用再改。

## 5. 和别的仓怎么连

- 新客户端字段：先在本仓 schema + 迁移，再改 Android / iOS。
- 新审核动作：同时改 `dating-web` 审核页。
- 活动默认待审，运营 `POST /admin/v1/activities/{id}/review` 后才公开。
