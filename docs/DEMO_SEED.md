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
