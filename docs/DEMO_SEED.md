# 演示数据种子

手动脚本（不挂 lifespan）：

```bash
cd dating-backend
python scripts/seed_content.py --base http://127.0.0.1:8000
# 公网验收前可对已部署 API：
# python scripts/seed_content.py --base http://123.56.118.242
```

幂等键：标题 / 内容前缀 `SEED·…`。重跑不会重复批准活动 `SEED·活动·18|19|20` 与帖子 `SEED·帖子·11|12`。

产出概览：8 用户 · 2 陪玩（服务 + 近 7 日档）· 20 活动（17 公开 + 3 待审）· 12 帖（10 公开 + 2 待审）· 好友会话预览 · 余额为 0 时运营发放 ¥500 · 货架挂公开活动。

试用步骤与账号见 Android 仓：[DEMO_GUIDE.md](../../dating-android/docs/DEMO_GUIDE.md)。

## 页面演示种子

`scripts/seed_pages.py` 与上面的冷启动脚本分开，标题前缀是 `DEMO·`，手机号 `13900007701`–`13900007710`，验证码仍是 `123456`。脚本运行时从网上下载封面图，再走 `/api/v1/media` 上传。

```bash
cd /work_place/dating-backend
python3 scripts/seed_pages.py --base http://127.0.0.1:8000
```

宿主机没有 Python 时：

```bash
docker cp /work_place/dating-backend/scripts/seed_pages.py dating-api:/tmp/seed_pages.py
docker exec dating-api python /tmp/seed_pages.py --base http://127.0.0.1:8000
```

会补上各分类活动、广场帖子（含待审）、陪玩服务与一笔完成的预约、报名/评论/点赞、好友和发现货架。可重复执行。需要当前后端已包含 `POST /admin/v1/wallet/grant`。
