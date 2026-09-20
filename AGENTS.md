# dating-backend · Agent

FastAPI 模块化单体。客户端与运营后台的 **唯一 HTTP 合同**。

## 边界

- 客户端：`/api/v1/*`（短信登录，开发码 `123456`）
- 运营：`/admin/v1/*`（账号密码，种子 `admin`）
- 响应：`{ "code": 0, "message": "...", "data": ... }`，失败 `code !== 0`
- 不要在本仓写 React / Android UI。合同变了，到 `dating-web`、`dating-android`（及 iOS）改消费方。

## 模块

`app/modules/`：`auth` · `user` · `media` · discover/swipe · reports/blocks · `activities` · `community`。共享能力在 `app/shared/`。表结构变更只走 Alembic，禁止手改生产库。

## 改接口时

1. 先改路由与 schema，保持字段命名与现有 JSON 风格（snake_case）。
2. 本地 `docker compose up -d --build`，打开 `/docs` 核对。
3. 跑对应 `scripts/smoke_*.ps1`。
4. 在回复里写清：Android `DatingApi` / 运营 `src/api/` / iOS 是否要跟。
5. 活动发布默认待审，运营审核后才进信息流。不要为了方便把待审改成直接公开，除非产品明确要求。

## 部署

服务器：`/work_place/dating-backend`。发版见 [docs/OPS.md](./docs/OPS.md)。禁止 `docker compose down -v` 打到 `wp_postgres` / `wp_redis`。不提交 `.env`。
