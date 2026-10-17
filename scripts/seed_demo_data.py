#!/usr/bin/env python
"""Realistic demo / test data for the whole app (users, activities, plaza, clubs, orders, ops queues, analytics).

Talks to the database through the app's own ORM models (no HTTP, no running API needed) and writes generated
images into the backend's media directory using the same key / URL scheme as ``LocalStorageDriver``.

    docker cp scripts/seed_demo_data.py dating-api:/tmp/seed_demo_data.py
    docker compose exec -w /app api python /tmp/seed_demo_data.py              # seed (idempotent)
    docker compose exec -w /app api python /tmp/seed_demo_data.py --reset      # remove ONLY seeded data

Every seeded row has a UUID starting with ``5eed5eed-`` (users also use phones 186 0000 0001..), so
``--reset`` is exact and never touches real data. See docs/SEED_DATA.md.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import struct
import sys
import zlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent, Path.cwd(), Path("/app")):
    if (_p / "app").is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SEED_PREFIX = "5eed5eed"
SEED_LIKE = SEED_PREFIX + "-%"
PHONE_BASE = 18600000000  # user i -> 186000000NN  (i >= 1)
DEFAULT_PASSWORD = "Seed@123456"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def sid(kind: str, key) -> UUID:
    """Deterministic seed UUID: 5eed5eed-xxxx-... (identifiable prefix, stable across runs)."""
    raw = bytearray(hashlib.md5(f"{kind}:{key}".encode()).digest())
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes.fromhex(SEED_PREFIX) + bytes(raw[:12]))


def ago(days: float = 0, hours: float = 0, minutes: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours, minutes=minutes)


def ahead(days: float = 0, hours: float = 0) -> datetime:
    return NOW + timedelta(days=days, hours=hours)


# ───────────────────────── static pools ─────────────────────────
SURNAMES = [("林", "L"), ("周", "Z"), ("苏", "S"), ("陈", "C"), ("何", "H"), ("顾", "G"), ("叶", "Y"), ("陆", "L"),
            ("沈", "S"), ("许", "X"), ("江", "J"), ("唐", "T"), ("宋", "S"), ("郑", "Z"), ("韩", "H"), ("程", "C"),
            ("徐", "X"), ("梁", "L"), ("傅", "F"), ("温", "W")]
GIVEN_F = [("夏", "X"), ("晚", "W"), ("宁", "N"), ("知意", "Z"), ("可心", "K"), ("星野", "X"), ("映雪", "Y"),
           ("微澜", "W"), ("清欢", "Q"), ("若溪", "R"), ("小满", "X"), ("暖暖", "N"), ("橙子", "C"), ("七月", "Q"),
           ("南枝", "N"), ("安然", "A")]
GIVEN_M = [("然", "R"), ("屿", "Y"), ("泽", "Z"), ("澄", "C"), ("安", "A"), ("嘉树", "J"), ("子墨", "Z"),
           ("景行", "J"), ("以安", "Y"), ("远舟", "Y"), ("朗", "L"), ("柏舟", "B"), ("川", "C"), ("逸尘", "Y"),
           ("砚秋", "Y"), ("时予", "S")]
NICKNAMES = ["橙子不吃香菜", "夜跑小分队", "周末只想躺平", "咖啡续命中", "胶片收藏家", "今天也要出片", "羽球狂热者",
             "火锅永远在线", "city walk 选手", "徒步到天亮", "剧本杀老炮", "晚风与猫", "慢慢来比较快", "山河远阔"]
CITIES = [("上海", 3.0, 31.2304, 121.4737), ("成都", 2.0, 30.5728, 104.0668), ("杭州", 1.5, 30.2741, 120.1551),
          ("北京", 1.5, 39.9042, 116.4074), ("广州", 1.0, 23.1291, 113.2644), ("深圳", 1.0, 22.5431, 114.0579),
          ("南京", 0.6, 32.0603, 118.7969), ("武汉", 0.6, 30.5928, 114.3055)]
CITY_COORD = {c: (la, ln) for c, _, la, ln in CITIES}
TAGS = ["摄影", "咖啡", "徒步", "阅读", "健身", "美食", "音乐", "火锅", "猫咪", "滑板", "旅行", "艺术", "纪录片",
        "展览", "烹饪", "骑行", "设计", "海边", "篮球", "电影", "羽毛球", "桌游", "剧本杀", "露营", "夜跑", "瑜伽",
        "狗狗", "手作", "City Walk", "游泳", "网球", "攀岩", "唱歌", "Livehouse"]
BIOS = [
    "{occ}，喜欢{t1}和{t2}。周末想找人一起出门走走。",
    "在{city}生活的第 {n} 年，{t1}爱好者，偶尔也玩{t2}。",
    "慢热但靠谱，{t1}、{t2}都可以聊。不爱迟到。",
    "想认识同城的搭子，一起{t1}，顺便{t2}。",
    "工作日写代码，周末{t1}。{t2}新手也欢迎！",
    "{t1}重度用户，正在学{t2}，求带。",
    "社恐但是约起来很准时，主要目的：{t1}。",
    "{city}本地人，熟悉{t1}的好去处，也想试试{t2}。",
]
OCCUPATIONS = ["学生", "上班", "上班", "上班", "自由职业", "其他"]
RADII = ["同城见面", "同城见面", "可跨城", "仅线上先聊"]
MBTIS = ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP", "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP",
         "ISFP", "ESTP", "ESFP"]
ZODIAC_EDGES = [(1, 20, "摩羯座"), (2, 19, "水瓶座"), (3, 21, "双鱼座"), (4, 20, "白羊座"), (5, 21, "金牛座"),
                (6, 22, "双子座"), (7, 23, "巨蟹座"), (8, 23, "狮子座"), (9, 23, "处女座"), (10, 24, "天秤座"),
                (11, 23, "天蝎座"), (12, 22, "射手座")]


def zodiac_of(b: date) -> str:
    for i, (m, d, name) in enumerate(ZODIAC_EDGES):
        if (b.month, b.day) < (m, d):
            return name if i > 0 else "摩羯座"
    return "射手座" if (b.month, b.day) < (12, 22) else "摩羯座"


# category -> (title list, summary, motif). Codes are the backend CATEGORIES set.
ACTIVITY_SPECS = [
    # key, category, title, city-hint, venue, fee_type, fee_cents, capacity, summary, state
    ("hotpot", "food", "周五火锅局｜六人拼桌不踩雷", "上海", "静安嘉里中心", "aa_offline", 0, 6, "控辣控预算，先到先坐，人均 100 左右 AA。", "open"),
    ("brunch", "food", "周日早茶｜广式点心打卡", "广州", "上下九步行街", "online_pay", 6800, 8, "费用含茶位和点心套餐，准时开桌。", "open"),
    ("bbq", "food", "江边烧烤夜｜自带好心情", "杭州", "钱塘江滨", "aa_offline", 0, 10, "食材现场分摊，酒水自理，不劝酒。", "open"),
    ("badminton", "sport", "进阶羽毛球双打｜自带拍", "成都", "高新体育馆", "aa_offline", 4000, 8, "场地费 AA，水平在 3.0-3.5，赛后一起吃饭。", "open"),
    ("nightride", "sport", "滨江夜骑 20km｜配速友好", "杭州", "钱塘江岸", "free", 0, 12, "休闲骑，有头盔更好，新手跟队不掉队。", "open"),
    ("basketball", "sport", "半场三对三｜输的请饮料", "上海", "徐家汇体育公园", "free", 0, 6, "友谊局，强度中等，不接受恶意犯规。", "full"),
    ("yoga", "sport", "晨间瑜伽｜公园草坪", "北京", "朝阳公园", "online_pay", 3900, 15, "含教练课时费，自带瑜伽垫。", "open"),
    ("westlake", "travel", "西湖半日慢走｜不赶景点", "杭州", "断桥残雪", "free", 0, 8, "步行 + 拍照，边走边聊，适合第一次来的朋友。", "open"),
    ("museum", "travel", "上海博物馆东馆｜预约入场", "上海", "世纪大道", "free", 0, 6, "集合后一起入场，自由参观后咖啡复盘。", "open"),
    ("citywall", "travel", "南京城墙骑行+徒步", "南京", "中华门", "online_pay", 3000, 10, "门票自理，集合后一起走完全程。", "open"),
    ("murder", "game", "情感本剧本杀｜6 人满员开", "深圳", "海岸城店", "online_pay", 12800, 6, "含主持和场地，新手友好，请勿剧透。", "open"),
    ("boardgame", "game", "桌游夜｜阿瓦隆 + 卡坦", "北京", "五道口桌游吧", "aa_offline", 0, 8, "最低消费 AA，新手可来。", "open"),
    ("lol", "game", "语音开黑｜排位找队友", "广州", "线上", "free", 0, 5, "段位不限，不喷人，晚上 9 点开。", "open"),
    ("study", "study", "静音自习室｜三小时专注", "北京", "国图附近咖啡馆", "free", 0, 6, "到场静音，番茄钟 50+10。", "open"),
    ("english", "study", "英语角｜中英夹杂不考试", "上海", "徐汇滨江", "free", 0, 10, "话题自由，口语不好也欢迎。", "open"),
    ("hike", "outdoors", "龙泉山徒步｜轻装看花", "成都", "龙泉驿", "free", 0, 15, "全程 8km，节奏慢，重点呼吸和拍照。", "open"),
    ("camp", "outdoors", "周末露营｜星空与烤棉花糖", "杭州", "富阳露营地", "online_pay", 15800, 12, "含营位和基础装备租赁，晚间有篝火。", "open"),
    ("climb", "outdoors", "室内攀岩体验课", "深圳", "南山攀岩馆", "online_pay", 9900, 8, "含教练和鞋租赁，零基础可参加。", "open"),
    ("photo", "other", "胶片扫街｜老城区出片", "成都", "宽窄巷子", "free", 0, 8, "带什么机器都行，路上互相拍。", "open"),
    ("pottery", "other", "陶艺手作体验｜做一只杯子", "上海", "安福路工作室", "online_pay", 18800, 6, "含材料和烧制，两周后取件。", "open"),
    ("livehouse", "other", "Livehouse 拼团看演出", "武汉", "光谷", "aa_offline", 0, 6, "各自买票，座位尽量挨着，散场一起宵夜。", "open"),
    ("pastbbq", "food", "上周日烧烤局（已结束）", "上海", "滨江公园", "aa_offline", 0, 8, "已结束的活动，用于测试历史记录。", "past"),
    ("pastride", "sport", "上周末夜跑 5km（已结束）", "成都", "锦江绿道", "free", 0, 10, "已结束的活动，可评论回顾。", "past"),
    ("cancelled", "travel", "周末郊游（天气原因取消）", "杭州", "九溪", "online_pay", 5800, 8, "因暴雨取消，已发起退款。", "cancelled"),
    ("pending1", "food", "待审核探店局：玉林路小酒馆", "成都", "玉林路", "free", 0, 4, "等待运营审核的活动。", "pending"),
    ("pending2", "game", "待审核：密室逃脱组队", "深圳", "福田", "online_pay", 8800, 6, "等待运营审核的活动。", "pending"),
    ("rejected", "other", "加微信领福利（违规示例）", "上海", "线上", "free", 0, 50, "含引流信息，已被运营驳回。", "rejected"),
]
ACTIVITY_TIMELINES = [
    [("14:00", "集合签到", "到场后在群里报个到"), ("14:30", "出发 / 开始", "准时开始"), ("17:30", "自由交流", "合影、留联系方式"), ("18:30", "散场", "注意安全")],
    [("09:30", "集合", "地铁口集合"), ("10:00", "出发", "全程约 3 小时"), ("13:00", "午餐", "AA")],
]
GEAR = ["舒适的鞋子", "饮用水", "充电宝", "防晒用品", "轻便外套"]
COMMENTS_ACT = ["报名了，期待！", "请问可以带朋友吗？", "新手可以参加吗？", "上次来过，体验很好", "集合点在哪个出口？",
                "已加群，周末见", "有没有同城的女生一起？", "价格很公道", "天气不好会改期吗？", "占位，等通知",
                "组织者很靠谱", "第一次参加，有点紧张哈哈"]
POST_TEXTS = [
    "周末终于去了心心念念的展，人少好拍，推荐大家工作日去 📷", "夜骑完在江边喝了杯咖啡，风很舒服",
    "今天的火锅局认识了三个新朋友，约好下次一起打羽毛球", "第一次尝试攀岩，手臂现在还在抖😂",
    "城市漫步路线分享：从老城到江边，大概 6 公里，沿途好多小店", "有人周末想一起露营吗？目前有两个人了",
    "剧本杀新手村毕业，原来真的会上头", "分享一下最近在练的曲子，欢迎同好交流 🎸",
    "晨跑打卡第 21 天，终于不喘了", "找个周日一起去逛市集的搭子，不赶行程，慢慢逛",
    "今天做了人生第一个陶杯，歪歪扭扭但很可爱", "雨天适合窝在咖啡店看书，有同好吗",
    "拍到一张满意的日落，海边的云太绝了", "新手徒步装备清单整理好了，评论区放",
    "推荐一家藏在巷子里的面馆，老板记得每个熟客的口味", "周五下班后有人想去 livehouse 吗",
]
POST_COMMENTS = ["太好看了！", "哈哈同感", "求具体地址", "mark 一下", "下次叫上我", "拍得真好", "有同城的吗？", "冲冲冲",
                 "已关注，期待更多分享", "这个我也想去", "好治愈", "收藏了，谢谢分享"]
CLUB_SPECS = [
    ("city_walk", "City Walk 研究所", "玩乐", "上海 · 徐汇", ["漫步", "探店", "拍照"], "bag", "每周一条新路线，边走边拍边聊。"),
    ("run", "晨跑打卡团", "运动", "杭州 · 西湖", ["晨跑", "打卡", "配速"], "figure.run", "5:30 起床困难户互相监督，配速分组。"),
    ("script", "周末剧本杀联盟", "娱乐", "深圳 · 南山", ["剧本杀", "桌游"], "theatermasks", "拼车组局，新手友好，反对剧透。"),
    ("climb", "攀岩新手互助", "户外", "北京 · 朝阳", ["攀岩", "抱石", "入门"], "figure.hiking", "共享装备与团课优惠，教练答疑。"),
    ("cafe", "咖啡探店小分队", "美食", "成都 · 锦江", ["咖啡", "探店", "甜品"], "cup.and.saucer", "每月一次集体探店，评分表公开。"),
    ("film", "胶片摄影交流会", "玩乐", "广州 · 越秀", ["摄影", "胶片", "扫街"], "camera", "晒片、交换底片、约拍。"),
]
GUILD_SPECS = [
    ("g_ride", "夜骑私教联盟（演示）", "骑行陪玩", "上海 · 浦东", ["夜骑", "私教"], "bicycle", 12800, "认证领队，一对一配速陪骑。"),
    ("g_game", "开黑上分小队（演示）", "游戏陪玩", "成都 · 高新区", ["开黑", "上分"], "gamecontroller", 6800, "语音陪玩，稳定在线。"),
    ("g_photo", "出片摄影陪拍社（演示）", "摄影陪玩", "杭州 · 西湖", ["跟拍", "修图"], "camera", 18800, "半日跟拍 + 精修 9 张。"),
]
COMPANION_SERVICES = {
    "voice": [("语音聊天陪伴", "half_hour", 3800, "轻松聊天，可以听你吐槽也可以一起听歌。"), ("语音开黑上分", "hour", 6800, "王者/LOL/和平精英，说话不嘴硬。")],
    "sport": [("羽毛球陪练", "hour", 9800, "按水平分档，场地费另计。"), ("夜跑陪跑", "hour", 6800, "配速友好，跑后拉伸指导。"), ("骑行领队", "session", 15800, "含路线规划与全程陪骑。")],
    "offline": [("探店陪吃", "session", 13800, "熟门熟路，控预算不劝酒。"), ("City Walk 向导", "half_hour", 5800, "老城区路线讲解 + 拍照。")],
    "photo": [("半日跟拍", "session", 28800, "含 30 张精修，当天出直出图。"), ("证件/形象照", "session", 19800, "含布光和修图 5 张。")],
}
SPECIALTIES = {"voice": "声音陪伴", "sport": "运动陪练", "offline": "线下陪玩", "photo": "摄影陪拍"}
REVIEWS = ["准时又靠谱，聊得很开心", "非常专业，下次还约", "体验很棒，推荐", "整体不错，就是时间稍紧", "性价比高，耐心细致", "超级有趣的小伙伴"]
REPORT_SPECS = [
    ("user", "spam", "频繁发送广告链接", "pending"), ("user", "harassment", "私信里言语骚扰", "pending"),
    ("post", "inappropriate", "动态含不当内容", "pending"), ("post", "spam", "发布微商引流", "pending"),
    ("activity", "fake", "活动信息不真实，疑似诱导付费", "pending"), ("comment", "harassment", "评论辱骂他人", "pending"),
    ("club", "inappropriate", "俱乐部简介含敏感信息", "pending"), ("user", "fake", "头像盗用他人照片", "pending"),
    ("user", "spam", "拉人进群推广", "resolved"), ("post", "inappropriate", "低俗内容", "resolved"),
    ("activity", "other", "组织者爽约", "dismissed"), ("user", "harassment", "恶意骚扰（已封禁）", "resolved"),
]
NOTIFY_TEMPLATES = [
    ("activity", "报名成功", "你已成功报名「{t}」，别忘了准时参加～", "spark://activity/{id}"),
    ("activity", "活动即将开始", "「{t}」将于明天开始，请提前规划出行。", "spark://activity/{id}"),
    ("buddy", "有人想和你做搭子", "{n} 向你打了个招呼，去看看吧。", "spark://friends"),
    ("booking", "预约已确认", "陪玩师已确认你的预约，请在 30 分钟内完成支付。", "spark://companion"),
    ("message", "新的好友申请", "{n} 请求添加你为好友。", "spark://friends"),
    ("community", "你的动态收到了新点赞", "{n} 赞了你的动态。", "spark://post/{id}"),
    ("system", "欢迎来到 Spark", "完善资料可获得更多推荐，试试发布第一个活动吧。", None),
    ("system", "账号安全提醒", "检测到你在新设备登录，如非本人操作请及时修改密码。", None),
]
ANNOUNCEMENTS = [
    ("【演示】平台社区公约更新", "为了营造友好的线下社交环境，我们更新了社区公约：禁止诱导转账、禁止泄露他人隐私、线下见面请选公共场所。", True, "published"),
    ("【演示】国庆活动季：发布活动赢曝光", "活动季期间发布并成功举办的活动，将有机会进入首页「编辑精选」。", False, "published"),
    ("【演示】系统维护通知", "本周日凌晨 2:00-4:00 进行例行维护，期间部分功能可能短暂不可用。", False, "published"),
    ("【演示】新版本功能预告（草稿）", "即将上线：活动行程、群公告、聊天撤回与编辑。", False, "draft"),
    ("【演示】已过期的双十一预热", "该公告已归档，用于测试后台归档列表。", False, "archived"),
]
FEEDBACKS = [("bug", "活动详情页偶尔加载很慢，网络正常。", "open", None), ("suggest", "希望增加按距离筛选活动。", "open", None),
             ("general", "整体体验很好，期待更多城市。", "replied", "感谢反馈，后续会逐步开放更多城市。"),
             ("bug", "充值后余额没有立即更新。", "closed", "已为你核实，余额已到账。")]


def zh_wrap(font, text: str, max_w: int, max_lines: int = 2) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if font.getlength(cur + ch) > max_w and cur:
            lines.append(cur)
            cur = ch
            if len(lines) == max_lines:
                break
        else:
            cur += ch
    if len(lines) < max_lines and cur:
        lines.append(cur)
    if len(lines) == max_lines and "".join(lines) != text:
        lines[-1] = lines[-1][:-1] + "…"
    return lines


# ───────────────────────── image generation ─────────────────────────
PALETTES = [((255, 154, 139), (255, 106, 136)), ((161, 140, 209), (251, 194, 235)), ((67, 206, 162), (24, 90, 157)),
            ((255, 200, 160), (252, 140, 120)), ((79, 172, 254), (0, 242, 254)), ((250, 112, 154), (254, 200, 64)),
            ((48, 207, 208), (51, 8, 103)), ((255, 175, 189), (255, 195, 160)), ((100, 220, 160), (60, 150, 210)),
            ((246, 190, 90), (253, 130, 110)), ((102, 126, 234), (118, 75, 162)), ((255, 126, 95), (254, 180, 123))]
MOTIF_BY_CAT = {"sport": "rings", "outdoors": "mountains", "food": "plates", "travel": "waves", "game": "dots",
                "study": "stripes", "other": "circles", "avatar": "bokeh", "post": "circles"}
CAT_LATIN = {"sport": "SPORT", "outdoors": "OUTDOOR", "food": "FOOD", "travel": "TRAVEL", "game": "GAME",
             "study": "STUDY", "other": "MEET UP"}
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf", "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
]
LATIN_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
               "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


class ImageFactory:
    """Writes files exactly where LocalStorageDriver would: {root}/{media_type}/{owner_id}/{hex}.{ext}."""

    def __init__(self, root: Path | None, public_base: str, enabled: bool, font: str | None = None):
        self.root, self.base, self.enabled = root, public_base.rstrip("/"), enabled
        self.files: list[Path] = []
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401

            self.pil = True
        except Exception:
            self.pil = False
        self._fonts: dict = {}
        self.cjk_path = None
        self.latin_path = None
        if self.enabled and self.pil:
            for cand in ([font] if font else []) + FONT_CANDIDATES:
                if cand and Path(cand).exists():
                    self.cjk_path = cand
                    break
            for cand in LATIN_FONTS:
                if Path(cand).exists():
                    self.latin_path = cand
                    break

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        if not self.pil:
            return "pure-python PNG gradients (Pillow not installed)"
        return f"Pillow ({'CJK font ' + Path(self.cjk_path).name if self.cjk_path else 'no CJK font → Latin labels'})"

    def font(self, size: int, cjk: bool):
        from PIL import ImageFont

        path = self.cjk_path if cjk and self.cjk_path else self.latin_path
        key = (path, size)
        if key not in self._fonts:
            try:
                self._fonts[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
            except Exception:
                self._fonts[key] = ImageFont.load_default()
        return self._fonts[key]

    # -- public --
    def make(self, media_type: str, owner_id: UUID, key: str, *, kind: str, cat: str = "other", text: str = "", latin: str = "",
             idx: int = 0, size: tuple[int, int] | None = None) -> dict | None:
        """kind: avatar | cover | post. Returns dict(object_key, url, width, height, bytes) or None when disabled."""
        if not self.enabled or self.root is None:
            return None
        rnd = random.Random(f"img:{key}")
        c1, c2 = PALETTES[(idx + rnd.randrange(len(PALETTES))) % len(PALETTES)]
        if kind == "avatar":
            size = size or (400, 400)
        elif kind == "cover":
            size = size or (960, 540)
        else:
            size = size or rnd.choice([(800, 800), (800, 600), (600, 800), (800, 800)])
        ext = "jpg" if self.pil else "png"
        object_key = f"{media_type}/{owner_id}/{hashlib.md5(key.encode()).hexdigest()}.{ext}"
        path = self.root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._render_pil(kind, size, c1, c2, rnd, cat, text, latin) if self.pil else self._render_png(size, c1, c2, rnd)
        path.write_bytes(data)
        self.files.append(path)
        return {"object_key": object_key, "url": f"{self.base}/media/{object_key}", "width": size[0],
                "height": size[1], "bytes": len(data), "mime": "image/jpeg" if self.pil else "image/png"}

    # -- Pillow renderer --
    def _render_pil(self, kind, size, c1, c2, rnd, cat, text, latin) -> bytes:
        import io

        from PIL import Image, ImageDraw, ImageFilter

        w, h = size
        mask = Image.linear_gradient("L")
        if rnd.random() < 0.5:
            mask = mask.transpose(Image.Transpose.ROTATE_90)
        mask = mask.resize(size)
        if rnd.random() < 0.3:
            mask = Image.radial_gradient("L").resize(size)
        img = Image.composite(Image.new("RGB", size, c2), Image.new("RGB", size, c1), mask).convert("RGBA")
        ov = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        motif = MOTIF_BY_CAT.get(cat if cat in MOTIF_BY_CAT else "other", "circles")
        if kind == "avatar":
            motif = "bokeh"
        if motif in ("circles", "bokeh", "plates"):
            for _ in range(rnd.randint(4, 8)):
                r = rnd.randint(int(min(w, h) * .08), int(min(w, h) * .3))
                x, y = rnd.randint(-r // 2, w), rnd.randint(-r // 2, h)
                a = rnd.randint(30, 80)
                if motif == "plates" and rnd.random() < .6:
                    d.ellipse((x, y, x + r, y + r), outline=(255, 255, 255, a + 60), width=max(3, r // 14))
                else:
                    d.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, a))
        elif motif == "rings":
            cx, cy = rnd.randint(w // 3, w), rnd.randint(0, h)
            for i in range(1, 6):
                r = i * min(w, h) // 6
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 90), width=max(3, w // 90))
        elif motif == "mountains":
            for layer, alpha in enumerate((70, 110, 160)):
                base = h * (0.55 + 0.12 * layer)
                pts = [(0, h)]
                x = -rnd.randint(0, w // 6)
                while x < w + w // 6:
                    pts.append((x, base - rnd.randint(int(h * .08), int(h * .3))))
                    x += rnd.randint(w // 6, w // 3)
                    pts.append((x, base + rnd.randint(0, int(h * .05))))
                pts.append((w, h))
                d.polygon(pts, fill=(255, 255, 255, alpha))
            d.ellipse((w * .72, h * .12, w * .72 + h * .18, h * .12 + h * .18), fill=(255, 255, 255, 190))
        elif motif == "waves":
            for layer in range(4):
                amp, off = h * .05 + layer * 4, h * (.45 + layer * .13)
                pts = [(x, off + amp * math.sin(x / (w / (3 + layer)) + layer * 1.3)) for x in range(0, w + 8, 8)]
                d.polygon(pts + [(w, h), (0, h)], fill=(255, 255, 255, 45 + layer * 25))
            d.ellipse((w * .15, h * .12, w * .15 + h * .2, h * .12 + h * .2), fill=(255, 255, 255, 170))
        elif motif == "dots":
            step = max(24, w // 18)
            for gx in range(step // 2, w, step):
                for gy in range(step // 2, h, step):
                    if rnd.random() < .45:
                        r = rnd.randint(3, step // 3)
                        d.ellipse((gx - r, gy - r, gx + r, gy + r), fill=(255, 255, 255, rnd.randint(50, 130)))
        elif motif == "stripes":
            step = max(30, w // 14)
            for x in range(-h, w, step):
                d.polygon([(x, h), (x + step // 2, h), (x + step // 2 + h, 0), (x + h, 0)], fill=(255, 255, 255, 50))
        img = Image.alpha_composite(img, ov.filter(ImageFilter.GaussianBlur(1.2) if motif == "bokeh" else ImageFilter.SMOOTH))
        cjk = bool(self.cjk_path)
        shown = text if cjk else (latin or "")
        layer = Image.new("RGBA", size, (0, 0, 0, 0))  # text/pills go on their own layer (real alpha blending)
        draw = ImageDraw.Draw(layer)
        if kind == "avatar" and shown:
            f = self.font(int(h * (0.42 if len(shown) <= 2 else 0.3)), cjk)
            bb = draw.textbbox((0, 0), shown, font=f)
            tx, ty = (w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]
            draw.text((tx + 3, ty + 4), shown, font=f, fill=(0, 0, 0, 55))
            draw.text((tx, ty), shown, font=f, fill=(255, 255, 255, 245))
        elif kind == "cover":
            for i in range(int(h * 0.5)):
                draw.line((0, h - i, w, h - i), fill=(0, 0, 0, int(150 * (1 - i / (h * 0.5)))))
            title = text if cjk and text else (latin or CAT_LATIN.get(cat, "MEET UP"))
            f = self.font(max(26, h // 11), cjk)
            lines = zh_wrap(f, title, int(w * 0.84)) if cjk else [title[:28]]
            y = h - int(h * 0.07) - len(lines) * int(h / 9.5)
            for ln in lines:
                draw.text((int(w * 0.06) + 2, y + 2), ln, font=f, fill=(0, 0, 0, 110))
                draw.text((int(w * 0.06), y), ln, font=f, fill=(255, 255, 255, 250))
                y += int(h / 9.5)
            tag = CAT_LATIN.get(cat, "MEET UP")
            tf = self.font(max(16, h // 22), False)
            tw = draw.textlength(tag, font=tf)
            draw.rounded_rectangle((w * 0.06, h * 0.07, w * 0.06 + tw + 28, h * 0.07 + h // 12), radius=h // 24, fill=(0, 0, 0, 70))
            draw.text((w * 0.06 + 14, h * 0.07 + h // 80), tag, font=tf, fill=(255, 255, 255, 245))
        img = Image.alpha_composite(img, layer)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=86)
        return buf.getvalue()

    # -- fallback renderer (no Pillow): diagonal gradient + a soft disc, PNG via zlib --
    def _render_png(self, size, c1, c2, rnd) -> bytes:
        w, h = max(120, size[0] // 3), max(120, size[1] // 3)
        cx, cy, r = rnd.randint(0, w), rnd.randint(0, h), min(w, h) // 3
        rows = bytearray()
        for y in range(h):
            rows.append(0)
            for x in range(w):
                t = (x / w + y / h) / 2
                px = [c1[i] + (c2[i] - c1[i]) * t for i in range(3)]
                if (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                    px = [v * 0.7 + 255 * 0.3 for v in px]
                rows += bytes(int(v) for v in px)

        def chunk(tag, body):
            c = struct.pack(">I", len(body)) + tag + body
            return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


# ───────────────────────── seeding engine ─────────────────────────
PKS = {"UserProfile": "user_id", "UserPreference": "user_id", "UserSettings": "user_id", "WalletAccount": "user_id",
       "CompanionProfile": "user_id", "ActivityDetail": "activity_id", "TrustScore": "user_id"}


class Seeder:
    def __init__(self, db, args, images: ImageFactory, rng: random.Random):
        self.db, self.a, self.img, self.rng = db, args, images, rng
        self.existing: dict = {}
        self.created: dict[str, int] = defaultdict(int)
        self.skipped: dict[str, int] = defaultdict(int)
        self.users: list[dict] = []
        self.acts: list[dict] = []
        self.posts: list[dict] = []
        self.clubs: list[dict] = []
        self.companions: list[dict] = []
        self.wallet_entries: dict[UUID, list] = defaultdict(list)
        self.media_created = 0

    # -- generic insert-if-absent --------------------------------------------------------------------------
    async def put(self, model, **kw):
        from sqlalchemy import String, cast, select

        name = model.__name__
        pk = PKS.get(name, "id")
        if getattr(self, "_last_model", None) is not model:
            await self.db.flush()  # parents (added earlier, other model) must hit the DB before children
            self._last_model = model
        if model not in self.existing:
            col = getattr(model, pk)
            rows = await self.db.execute(select(col).where(cast(col, String).like(SEED_LIKE)))
            self.existing[model] = {r[0] for r in rows}
        ex = self.existing[model]
        key = kw[pk]
        if key in ex:
            self.skipped[model.__tablename__] += 1
            return None
        ex.add(key)
        obj = model(**kw)
        self.db.add(obj)
        self.created[model.__tablename__] += 1
        return obj

    async def stage(self, label: str):
        await self.db.flush()
        await self.db.commit()
        print(f"  ✓ {label}")

    def media(self, owner: UUID, media_type: str, key: str, **imgkw):
        """Generate an image file (if enabled) and return (media_id, url, MediaAsset kwargs) or None."""
        info = self.img.make(media_type, owner, key, **imgkw)
        if info is None:
            return None
        mid = sid("media", key)
        return mid, info["url"], dict(
            id=mid, owner_id=owner, media_type=media_type, object_key=info["object_key"], url=info["url"],
            audit_status="approved",
            meta={"seed": True, "mime": info["mime"], "size_bytes": info["bytes"], "width": info["width"],
                  "height": info["height"], "generated": "pillow" if self.img.pil else "pure-python"},
            created_at=NOW)

    async def put_media(self, owner, media_type, key, **imgkw):
        res = self.media(owner, media_type, key, **imgkw)
        if res is None:
            return None
        from app.models import MediaAsset

        mid, url, kw = res
        await self.put(MediaAsset, **kw)
        self.media_created += 1
        return {"type": "image", "url": url, "media_id": str(mid)}, mid, url

    def pick_users(self, k: int, exclude: set | None = None, rng=None, pool=None) -> list[dict]:
        rng = rng or self.rng
        pool = [u for u in (pool or self.users) if u["status"] == "active" and (not exclude or u["id"] not in exclude)]
        return rng.sample(pool, min(k, len(pool)))

    # -- 0. bootstrap (what app startup does anyway; never deleted by --reset) -----------------------------
    async def bootstrap(self):
        from app.modules.clubs.seed import ensure_official_clubs
        from app.modules.commerce.seed import ensure_membership_plans
        from app.modules.ops.seed import ensure_default_taxonomies

        await ensure_default_taxonomies(self.db)
        await ensure_membership_plans(self.db)
        await ensure_official_clubs(self.db)
        print("  ✓ bootstrap (taxonomies / membership plans / official clubs ensured)")

    # -- 1. users ------------------------------------------------------------------------------------------
    async def seed_users(self, n: int, password: str):
        from sqlalchemy import select

        from app.models import (Device, MediaAsset, User, UserPreference, UserProfile, UserSettings)
        from app.modules.messaging.uid import derive_public_uid
        from app.shared.passwords import hash_password

        pw_hash = hash_password(password)
        taken_uid = {r[0] for r in await self.db.execute(select(User.public_uid).where(User.public_uid.is_not(None)))}
        used_names: set[str] = set()
        fixed = {1: ("林夏", "female", "上海", "L"), 2: ("周屿", "male", "上海", "Z"), 3: ("苏晚", "female", "成都", "S")}
        for i in range(1, n + 1):
            r = random.Random(f"{self.a.seed}:user:{i}")
            uid = sid("user", i)
            if i in fixed:
                name, gender, city, ini = fixed[i]
            else:
                gender = "female" if r.random() < 0.52 else "male"
                sn, si = r.choice(SURNAMES)
                gn, gi = r.choice(GIVEN_F if gender == "female" else GIVEN_M)
                name, ini = sn + gn, si + gi
                if r.random() < 0.25:
                    name = r.choice(NICKNAMES)
                    ini = "N" + str(i % 10)
                base = name
                while name in used_names:
                    name = f"{base}{r.randint(2, 99)}"
                city = r.choices([c[0] for c in CITIES], [c[1] for c in CITIES])[0]
            used_names.add(name)
            tags = r.sample(TAGS, r.randint(3, 6))
            age = r.randint(19, 38)
            birthday = date(NOW.year - age, r.randint(1, 12), r.randint(1, 28))
            occ = r.choice(OCCUPATIONS)
            status = "active"
            if n >= 12 and i == 11:
                status = "banned"
            elif n >= 12 and i == 12:
                status = "limited"
            created = ago(days=r.randint(3, 75) if i > 3 else 90 - i)
            pub = derive_public_uid(uid)
            while pub in taken_uid:
                pub = f"{(int(pub) + 1) % 1_000_000_000:09d}"
            taken_uid.add(pub)
            u = dict(id=uid, idx=i, phone=str(PHONE_BASE + i), name=name, initials=ini, gender=gender, city=city,
                     tags=tags, birthday=birthday, status=status, created=created, occ=occ, r=r,
                     lat=CITY_COORD[city][0], lng=CITY_COORD[city][1], avatar_url=None)
            self.users.append(u)
            await self.put(User, id=uid, phone=u["phone"], password_hash=pw_hash, public_uid=pub, status=status,
                           discoverable=status == "active", profile_completed=True, created_at=created,
                           last_active_at=ago(hours=r.choice([1, 3, 8, 20, 30, 50, 72, 200])))
        await self.db.flush()
        for u in self.users:
            r, uid, i = u["r"], u["id"], u["idx"]
            av = await self.put_media(uid, "avatar", f"avatar:{i}", kind="avatar", cat="avatar", text=u["name"][-1],
                                      latin=u["initials"], idx=i)
            avatar_id = av[1] if av else None
            u["avatar_url"] = av[2] if av else None
            if i % 3 == 0:
                for j in range(2):
                    await self.put_media(uid, "album", f"album:{i}:{j}", kind="post", cat="post", idx=i + j)
            h = r.randint(155, 172) if u["gender"] == "female" else r.randint(168, 188)
            bio = r.choice(BIOS).format(occ=u["occ"], t1=u["tags"][0], t2=u["tags"][1], city=u["city"], n=r.randint(1, 9))
            await self.put(UserProfile, user_id=uid, display_name=u["name"], birthday=u["birthday"], gender=u["gender"],
                           city=u["city"], bio=bio, tags=u["tags"], avatar_media_id=avatar_id,
                           completion_score=r.randint(78, 100), height_cm=h,
                           weight_kg=int(h * (0.33 if u["gender"] == "female" else 0.4) + r.randint(-4, 6)),
                           occupation=u["occ"], meet_radius=r.choice(RADII), mbti=r.choice(MBTIS),
                           zodiac=zodiac_of(u["birthday"]))
            await self.put(UserPreference, user_id=uid, want_genders=["male"] if u["gender"] == "female" else ["female"],
                           age_min=18, age_max=r.choice([35, 40, 45]), max_distance_km=r.choice([10, 30, 50, 100]))
            await self.put(UserSettings, user_id=uid, guidelines_ack_at=u["created"], legal_consent_at=u["created"])
            await self.put(Device, id=sid("device", i), user_id=uid, device_id=f"seed-device-{i:04d}",
                           platform=r.choice(["android", "android", "android", "ios"]),
                           created_at=u["created"], last_seen_at=ago(hours=r.randint(1, 72)))
        await self.stage(f"users ({n}) + profiles/avatars/preferences/settings/devices")

    # -- 2. trust / verified flags -------------------------------------------------------------------------
    async def seed_trust(self):
        from app.models import TrustBadge, TrustScore, Verification

        for u in self.users:
            r = random.Random(f"{self.a.seed}:trust:{u['idx']}")
            photo = u["idx"] <= 3 or r.random() < 0.5
            real = u["idx"] <= 2 or r.random() < 0.25
            phone = True
            u.update(photo_verified=photo, real_verified=real)
            if photo:
                await self.put(Verification, id=sid("verif", f"photo:{u['idx']}"), user_id=u["id"], kind="photo",
                               status="approved", similarity=Decimal(str(round(r.uniform(.82, .97), 3))),
                               quality_score=Decimal(str(round(r.uniform(.8, .98), 3))), reviewed_at=ago(days=r.randint(1, 30)),
                               created_at=ago(days=r.randint(31, 40)))
                await self.put(TrustBadge, id=sid("badge", f"photo:{u['idx']}"), user_id=u["id"], kind="photo_verified",
                               granted_at=ago(days=20), source="verification")
            if real:
                await self.put(Verification, id=sid("verif", f"real:{u['idx']}"), user_id=u["id"], kind="realname",
                               status="approved", reviewed_at=ago(days=r.randint(1, 30)), created_at=ago(days=r.randint(31, 40)))
                await self.put(TrustBadge, id=sid("badge", f"real:{u['idx']}"), user_id=u["id"], kind="identity_verified",
                               granted_at=ago(days=18), source="verification")
            if phone:
                await self.put(TrustBadge, id=sid("badge", f"phone:{u['idx']}"), user_id=u["id"], kind="phone_verified",
                               granted_at=u["created"], source="system")
            if u["idx"] % 7 == 0:
                await self.put(TrustBadge, id=sid("badge", f"active:{u['idx']}"), user_id=u["id"], kind="active_member",
                               granted_at=ago(days=5), source="system")
            score = 45 + 12 * photo + 18 * real + r.randint(0, 20)
            level = "reliable_host" if score >= 85 else "trusted" if score >= 70 else "newcomer"
            await self.put(TrustScore, user_id=u["id"], score=Decimal(score), level=level,
                           identity=Decimal(40 + 25 * photo + 30 * real), reliability=Decimal(r.randint(55, 95)),
                           communication=Decimal(r.randint(55, 95)), safety=Decimal(r.randint(60, 98)),
                           facts={"seed": True, "photo_verified": photo, "realname_verified": real},
                           computed_at=NOW, sample_size=r.randint(3, 30), confidence_low=score < 60)
        # ops queue samples: pending / rejected verifications from users that are not yet verified
        pend = [u for u in self.users if not u["photo_verified"] and u["status"] == "active"][:4]
        for k, u in enumerate(pend):
            await self.put(Verification, id=sid("verif", f"pending:{u['idx']}"), user_id=u["id"],
                           kind="photo" if k % 2 == 0 else "realname", status="pending",
                           similarity=Decimal("0.801") if k % 2 == 0 else None, created_at=ago(hours=3 + k * 5))
        if len(self.users) > 8:
            u = [x for x in self.users if not x["photo_verified"] and x["status"] == "active"][4:5]
            for x in u:
                await self.put(Verification, id=sid("verif", f"rej:{x['idx']}"), user_id=x["id"], kind="photo",
                               status="rejected", similarity=Decimal("0.412"), reject_reason="人脸与头像相似度不足，请重新拍摄",
                               reviewed_at=ago(days=1), created_at=ago(days=2))
        await self.stage("trust: verifications / badges / trust scores (+pending & rejected samples)")

    # -- 3. social graph / conversations ------------------------------------------------------------------
    async def seed_social(self):
        from app.models import (Block, BuddyGreeting, BuddyIntent, Conversation, ConversationMember, FriendRequest,
                                Friendship, Match, MessageRequest, Swipe, UserFollow)

        users = [u for u in self.users if u["status"] == "active"]
        by_idx = {u["idx"]: u for u in self.users}
        rng = random.Random(f"{self.a.seed}:social")
        # follows
        pairs = set()
        for u in users:
            for v in rng.sample(users, min(len(users), rng.randint(3, 10))):
                if v["id"] != u["id"]:
                    pairs.add((u["idx"], v["idx"]))
        for a, b in sorted(pairs):
            await self.put(UserFollow, id=sid("follow", f"{a}:{b}"), follower_id=by_idx[a]["id"], followee_id=by_idx[b]["id"],
                           created_at=ago(days=rng.randint(0, 40)))
        # friendships (bi-directional rows) – the 3 fixed accounts are friends with each other and many others
        fr: set[tuple[int, int]] = {(1, 2), (1, 3), (2, 3)} if len(self.users) >= 3 else set()
        for u in users:
            cnt = 8 if u["idx"] <= 3 else rng.randint(1, 4)
            for v in rng.sample(users, min(len(users), cnt)):
                if v["idx"] != u["idx"]:
                    fr.add(tuple(sorted((u["idx"], v["idx"]))))
        fr_sorted = sorted(fr)
        friends_of: dict[int, list[int]] = defaultdict(list)
        for a, b in fr_sorted:
            friends_of[a].append(b)
            friends_of[b].append(a)
            t = ago(days=rng.randint(1, 50))
            await self.put(Friendship, id=sid("friend", f"{a}>{b}"), user_id=by_idx[a]["id"], friend_id=by_idx[b]["id"],
                           remark=None, group_name=None, status="active", created_at=t)
            await self.put(Friendship, id=sid("friend", f"{b}>{a}"), user_id=by_idx[b]["id"], friend_id=by_idx[a]["id"],
                           remark=None, group_name=None, status="active", created_at=t)
            await self.put(FriendRequest, id=sid("freq", f"{a}>{b}"), from_user_id=by_idx[a]["id"], to_user_id=by_idx[b]["id"],
                           message="你好，一起约活动呀", source=rng.choice(["uid", "activity", "buddy"]), status="accepted",
                           created_at=t - timedelta(hours=2), responded_at=t)
        self.friends_of = friends_of
        # pending / declined friend requests addressed to main account
        non_friends = [u for u in users if u["idx"] != 1 and u["idx"] not in friends_of[1]]
        for k, u in enumerate(non_friends[:3]):
            await self.put(FriendRequest, id=sid("freq", f"pending:{u['idx']}>1"), from_user_id=u["id"],
                           to_user_id=by_idx[1]["id"], message=rng.choice(["看到你的活动，想认识一下", "同城搭子，加个好友吧", "你好～"]),
                           source=rng.choice(["uid", "activity"]), status="pending", created_at=ago(hours=2 + 9 * k))
        for k, u in enumerate(non_friends[3:5]):
            await self.put(FriendRequest, id=sid("freq", f"declined:{u['idx']}>1"), from_user_id=u["id"],
                           to_user_id=by_idx[1]["id"], message="加个好友", source="uid", status="declined",
                           created_at=ago(days=4 + k), responded_at=ago(days=3))
        # direct conversation shells (+ last message preview so the inbox looks alive)
        previews = ["哈哈好的，周六见", "[图片]", "那我们 2 点在地铁口集合？", "收到～", "谢谢你！下次再约", "我到啦，你在哪个出口？",
                    "今天玩得很开心", "可以呀，你定时间", "[语音 6″]", "晚点回你哈"]
        n_dm = 0
        for a, b in fr_sorted:
            if a > 3 and rng.random() > 0.5:
                continue
            ua, ub = by_idx[a], by_idx[b]
            cid = sid("conv", f"dm:{a}:{b}")
            t = ago(hours=rng.randint(1, 24 * 6))
            low, high = sorted([str(ua["id"]), str(ub["id"])])
            await self.put(Conversation, id=cid, kind="direct", im_conversation_id=f"noop_dm_{low[:8]}_{high[:8]}",
                           title=ub["name"], owner_id=ua["id"], last_message_preview=rng.choice(previews),
                           last_message_at=t, status="active", created_at=t - timedelta(days=2),
                           meta={"peer_names": {str(ua["id"]): ua["name"], str(ub["id"]): ub["name"]}, "seed": True})
            for who, role in ((ua, "owner"), (ub, "member")):
                await self.put(ConversationMember, id=sid("cmem", f"{cid}:{who['idx']}"), conversation_id=cid,
                               user_id=who["id"], role=role, unread_count=rng.choice([0, 0, 0, 1, 2, 5]) if who is ub else 0,
                               pinned=(who["idx"] == 1 and n_dm == 0), last_read_at=t, status="active",
                               joined_at=t - timedelta(days=2))
            n_dm += 1
        # a friends group chat
        g = [by_idx[i] for i in ([1, 2, 3] + friends_of[1][:3]) if i in by_idx]
        g = list({u["idx"]: u for u in g}.values())
        if len(g) >= 3:
            gid = sid("conv", "group:main")
            await self.put(Conversation, id=gid, kind="group", im_conversation_id=f"noop_group_{g[0]['id'].hex[:12]}",
                           title="周末搭子小分队", owner_id=g[0]["id"], last_message_preview="这周六有人去徒步吗？",
                           last_message_at=ago(hours=5), announcement="群公约：不迟到、不剧透、AA 清晰。", status="active",
                           created_at=ago(days=12), meta={"seed": True})
            for k, u in enumerate(g):
                await self.put(ConversationMember, id=sid("cmem", f"{gid}:{u['idx']}"), conversation_id=gid, user_id=u["id"],
                               role="owner" if k == 0 else "member", unread_count=0 if k == 0 else 3, status="active",
                               joined_at=ago(days=12))
        # message requests (stranger → main account)
        for k, u in enumerate(non_friends[5:7]):
            cid = sid("conv", f"req:{u['idx']}")
            await self.put(Conversation, id=cid, kind="direct", im_conversation_id=f"noop_dm_req{k}", title=by_idx[1]["name"],
                           owner_id=u["id"], last_message_preview="你好，看到你的动态想认识一下", last_message_at=ago(hours=4 + k),
                           status="active", created_at=ago(hours=5), meta={"is_message_request": True, "seed": True,
                                                                              "peer_names": {str(u["id"]): u["name"], str(by_idx[1]["id"]): by_idx[1]["name"]}})
            for who, role in ((u, "owner"), (by_idx[1], "member")):
                await self.put(ConversationMember, id=sid("cmem", f"{cid}:{who['idx']}"), conversation_id=cid, user_id=who["id"],
                               role=role, unread_count=1 if who["idx"] == 1 else 0, status="active", joined_at=ago(hours=5))
            await self.put(MessageRequest, id=sid("mreq", f"{u['idx']}>1"), conversation_id=cid, from_user_id=u["id"],
                           to_user_id=by_idx[1]["id"], preview_text="你好，看到你的动态想认识一下", source="direct_message",
                           status="pending", created_at=ago(hours=4 + k))
        # swipes / matches / blocks
        mm = 0
        for u in users[:30]:
            for v in rng.sample(users, min(6, len(users))):
                if v["idx"] == u["idx"]:
                    continue
                await self.put(Swipe, id=sid("swipe", f"{u['idx']}>{v['idx']}"), actor_id=u["id"], target_id=v["id"],
                               action="like" if rng.random() < 0.55 else "pass", created_at=ago(days=rng.randint(0, 20)))
        for a, b in fr_sorted[:12]:
            lo, hi = sorted([by_idx[a]["id"], by_idx[b]["id"]], key=lambda x: str(x))
            await self.put(Match, id=sid("match", f"{a}:{b}"), user_low=lo, user_high=hi, status="active",
                           matched_at=ago(days=rng.randint(1, 20)))
            mm += 1
        if len(users) > 14:
            await self.put(Block, id=sid("block", "5>6"), blocker_id=by_idx[5]["id"], blocked_id=by_idx[6]["id"], created_at=ago(days=3))
        # buddy (找人玩) intents + greetings
        for u in users:
            if u["idx"] % 4 == 1 or u["idx"] <= 3:
                await self.put(BuddyIntent, id=sid("intent", u["idx"]), user_id=u["id"],
                               text=rng.choice(["想找人周末一起徒步", "求一个羽毛球搭子", "找个人一起探店", "想去 livehouse，有人吗",
                                                "夜骑搭子在线等", "新手想学攀岩，求带"]),
                               tags=u["tags"][:3], city=u["city"], active=True, expires_at=ahead(days=rng.randint(3, 14)),
                               created_at=ago(days=rng.randint(0, 6)))
        for k, u in enumerate(self.pick_users(4, exclude={by_idx[1]["id"]}, rng=rng)):
            await self.put(BuddyGreeting, id=sid("greet", f"{u['idx']}>1"), from_user_id=u["id"], to_user_id=by_idx[1]["id"],
                           text=rng.choice(["嗨，也喜欢徒步吗？", "看到你想找羽毛球搭子～", "你好呀，同城搭子！"]),
                           status=["sent", "sent", "replied", "ignored"][k % 4], created_at=ago(hours=3 + 7 * k))
        await self.stage(f"social: {len(pairs)} follows, {len(fr_sorted)} friendships, {n_dm} DM shells, group chat, "
                         f"requests, swipes/matches, buddy intents")

    # -- 4. activities -------------------------------------------------------------------------------------
    async def seed_activities(self):
        from app.models import (Activity, ActivityComment, ActivityDetail, ActivityFavorite, ActivityJourney, ActivityLike,
                                ActivityParticipant, BuddyInvite, Conversation, ConversationMember)

        rng = random.Random(f"{self.a.seed}:activities")
        users = [u for u in self.users if u["status"] == "active"]
        by_idx = {u["idx"]: u for u in self.users}
        cap_total = len(users)
        for k, (key, cat, title, city, venue, fee_type, fee, cap, summary, state) in enumerate(ACTIVITY_SPECS):
            local = [u for u in users if u["city"] == city and u["idx"] > 3] or [u for u in users if u["idx"] > 3] or users
            host = by_idx[3] if k == 0 and 3 in by_idx else rng.choice(local)
            if k in (3, 4) and 1 in by_idx:
                host = by_idx[1]  # main account hosts a couple of activities
            aid = sid("activity", key)
            la, ln = CITY_COORD.get(city, (31.23, 121.47))
            if state == "past":
                start = ago(days=rng.randint(4, 9), hours=-rng.choice([9, 14, 19]) % 24)
            elif state == "cancelled":
                start = ahead(days=4)
            else:
                start = (NOW + timedelta(days=rng.randint(1, 20))).replace(hour=rng.choice([9, 10, 14, 15, 19]), minute=rng.choice([0, 30]))
            end = start + timedelta(hours=rng.choice([2, 3, 4]))
            created = start - timedelta(days=rng.randint(6, 18))
            if created > NOW:
                created = ago(days=1)
            status = {"open": "published", "full": "published", "past": "published", "cancelled": "cancelled",
                      "pending": "pending", "rejected": "rejected"}[state]
            # participants
            pool = [u for u in users if u["id"] != host["id"]]
            if state == "full":
                want = cap - 1
            elif state == "open":
                want = rng.randint(1, max(1, cap - 2))
            elif state == "past":
                want = rng.randint(3, max(3, cap - 1))
            elif state == "cancelled":
                want = 3
            else:
                want = 0
            members = rng.sample(pool, min(want, len(pool))) if want else []
            if state == "open" and 1 in by_idx and host["idx"] != 1 and k % 3 == 0 and by_idx[1] not in members:
                members = (members + [by_idx[1]])[: max(1, want)]
            waitlist = [u for u in rng.sample(pool, min(3, len(pool))) if u not in members][:2] if state == "full" else []
            media = []
            if self.img.enabled:
                for j in range(rng.choice([1, 2, 2, 3])):
                    m = await self.put_media(host["id"], "activity_image", f"act:{key}:{j}", kind="cover" if j == 0 else "post",
                                             cat=cat, text=title, latin=CAT_LATIN.get(cat, ""), idx=k + j,
                                             size=(960, 540) if j == 0 else (800, 600))
                    if m:
                        media.append(m[0])
            likes = rng.sample(users, min(len(users), rng.randint(2, 18)))
            favs = rng.sample(users, min(len(users), rng.randint(1, 8)))
            ncom = rng.randint(2, 6) if status == "published" else 0
            joined = len(members) + 1
            await self.put(Activity, id=aid, host_id=host["id"], title=title, description=summary + "\n\n欢迎准时到场，如有变动会在活动群里通知。",
                           category=cat, city=city, address=venue, lat=f"{la + rng.uniform(-.04, .04):.6f}",
                           lng=f"{ln + rng.uniform(-.04, .04):.6f}", start_at=start, end_at=end, capacity=cap, join_count=joined,
                           media=media, fee_type=fee_type, fee_cents=fee,
                           fee_note="场地费 AA" if fee_type == "aa_offline" and fee else ("线下 AA，现场结算" if fee_type == "aa_offline" else None),
                           cancel_reason="天气原因（暴雨预警）" if state == "cancelled" else None,
                           cancelled_at=ago(days=1) if state == "cancelled" else None, status=status,
                           like_count=len(likes) if status == "published" else 0, comment_count=ncom,
                           favorite_count=len(favs) if status == "published" else 0,
                           reviewed_at=created + timedelta(hours=3) if status in ("published", "rejected", "cancelled") else None,
                           admin_note="含引流联系方式，驳回" if state == "rejected" else None, created_at=created)
            a = dict(id=aid, key=key, title=title, cat=cat, city=city, host=host, fee_type=fee_type, fee=fee, state=state,
                     status=status, members=members, waitlist=waitlist, start=start, created=created, cap=cap)
            self.acts.append(a)
            tl = rng.choice(ACTIVITY_TIMELINES)
            await self.put(ActivityDetail, activity_id=aid,
                           timeline=[{"time": t, "title": ti, "note": (venue if i == 0 else note)} for i, (t, ti, note) in enumerate(tl)],
                           gear=rng.sample(GEAR, 3), fee_included=["组织与协调", "活动群与保险提醒"] if fee else ["组织与协调"],
                           fee_excluded=["往返交通", "个人餐饮"], refund_notes=["开始前 24 小时可全额退款", "开始前 24 小时内退款扣 20%"] if fee_type == "online_pay" else [],
                           prep_notes=["提前 10 分钟到", "下雨会提前通知改期"], registration_notes=["请使用真实头像", "未成年人请勿报名"],
                           host_note=summary, gallery=[])
            if status in ("pending", "rejected"):
                continue
            await self.put(ActivityParticipant, id=sid("apart", f"{key}:host"), activity_id=aid, user_id=host["id"], role="host",
                           status="joined", joined_at=created)
            for u in members:
                await self.put(ActivityParticipant, id=sid("apart", f"{key}:{u['idx']}"), activity_id=aid, user_id=u["id"],
                               role="member", status="joined", note=rng.choice([None, None, "第一次参加", "带一个朋友"]),
                               joined_at=created + timedelta(hours=rng.randint(2, 100)))
            for u in waitlist:
                await self.put(ActivityParticipant, id=sid("apart", f"{key}:{u['idx']}"), activity_id=aid, user_id=u["id"],
                               role="member", status="waitlisted", waitlisted_at=ago(hours=rng.randint(1, 30)),
                               joined_at=ago(hours=rng.randint(1, 30)))
            for u in likes:
                await self.put(ActivityLike, id=sid("alike", f"{key}:{u['idx']}"), activity_id=aid, user_id=u["id"], created_at=ago(days=rng.randint(0, 8)))
            for u in favs:
                await self.put(ActivityFavorite, id=sid("afav", f"{key}:{u['idx']}"), activity_id=aid, user_id=u["id"], created_at=ago(days=rng.randint(0, 8)))
            for c in range(ncom):
                au = rng.choice(members + [host]) if members else host
                await self.put(ActivityComment, id=sid("acom", f"{key}:{c}"), activity_id=aid, author_id=au["id"],
                               content=rng.choice(COMMENTS_ACT), status="visible", created_at=created + timedelta(hours=6 + c * 7))
            if state == "past":
                for u in members[:3]:
                    await self.put(ActivityJourney, id=sid("journey", f"{key}:{u['idx']}"), activity_id=aid, user_id=u["id"],
                                   steps={"departed": True, "arrived": True, "checked_in_at": (start + timedelta(minutes=5)).isoformat()},
                                   feedback={"rating": rng.randint(4, 5), "text": "组织得很好，下次还来"})
            if status == "published" and members:
                cid = sid("conv", f"act:{key}")
                await self.put(Conversation, id=cid, kind="activity", im_conversation_id=f"noop_group_{host['id'].hex[:12]}",
                               title=f"{title} · 活动群", owner_id=host["id"], related_activity_id=aid,
                               last_message_preview=rng.choice(["集合点已更新，请查看公告", "大家记得带水～", "我到啦", "今天辛苦大家！"]),
                               last_message_at=ago(hours=rng.randint(1, 48)), status="active", created_at=created + timedelta(hours=4),
                               announcement=f"集合地点：{venue}，请准时。", meta={"seed": True})
                for u in [host] + members:
                    await self.put(ConversationMember, id=sid("cmem", f"{cid}:{u['idx']}"), conversation_id=cid, user_id=u["id"],
                                   role="owner" if u is host else "member", unread_count=0 if u is host else rng.choice([0, 0, 2, 7]),
                                   status="active", joined_at=created + timedelta(hours=5))
        # invitations for the main account
        opens = [a for a in self.acts if a["state"] == "open" and a["host"]["idx"] != 1 and by_idx[1] not in a["members"]]
        for k, a in enumerate(opens[:3]):
            await self.put(BuddyInvite, id=sid("invite", f"{a['key']}>1"), from_user_id=a["host"]["id"], to_user_id=by_idx[1]["id"],
                           activity_id=a["id"], message="来参加吧，缺一个人～", status="pending" if k < 2 else "declined",
                           created_at=ago(hours=6 + 10 * k))
        await self.stage(f"activities ({len(self.acts)}): details, participants, comments, likes, group chats, journeys, invites")

    # -- 5. plaza ------------------------------------------------------------------------------------------
    async def seed_posts(self):
        from app.models import CommunityBookmark, CommunityComment, CommunityLike, CommunityPost, CommunityRepost

        rng = random.Random(f"{self.a.seed}:posts")
        users = [u for u in self.users if u["status"] == "active"]
        count = max(8, int(len(self.users) * 1.2))
        n_media = 0
        for i in range(count):
            au = users[i % 3] if i < 6 else rng.choice(users)  # main accounts have content too
            pid = sid("post", i)
            created = ago(days=rng.random() * 14)
            status = "published"
            if i % 29 == 7:
                status = "pending"
            elif i % 41 == 13:
                status = "rejected"
            media = []
            if self.img.enabled:
                for j in range(rng.choices([0, 1, 2, 3, 4, 6], [2, 4, 3, 2, 1, 1])[0]):
                    m = await self.put_media(au["id"], "post_image", f"post:{i}:{j}", kind="post", cat="post", idx=i + j)
                    if m:
                        media.append(m[0])
                        n_media += 1
            likers = rng.sample(users, min(len(users), rng.randint(0, 25))) if status == "published" else []
            marks = [u for u in likers if rng.random() < 0.25]
            reposts = [u for u in likers if rng.random() < 0.1]
            ncom = rng.randint(0, 5) if status == "published" else 0
            text = POST_TEXTS[i % len(POST_TEXTS)] if i < len(POST_TEXTS) else rng.choice(POST_TEXTS)
            await self.put(CommunityPost, id=pid, author_id=au["id"],
                           content=text if status != "rejected" else "加我微信看更多福利 vx: demo123 （违规示例）",
                           media=media, status=status, like_count=len(likers), comment_count=ncom,
                           bookmark_count=len(marks), repost_count=len(reposts),
                           reviewed_at=created + timedelta(hours=1) if status in ("published", "rejected") else None,
                           admin_note="含引流信息，驳回" if status == "rejected" else None, created_at=created)
            self.posts.append(dict(id=pid, author=au, status=status, text=text, ncom=ncom, i=i))
            for u in likers:
                await self.put(CommunityLike, id=sid("plike", f"{i}:{u['idx']}"), post_id=pid, user_id=u["id"],
                               created_at=created + timedelta(hours=rng.randint(1, 60)))
            for u in marks:
                await self.put(CommunityBookmark, id=sid("pmark", f"{i}:{u['idx']}"), post_id=pid, user_id=u["id"],
                               collection_name="default", created_at=created + timedelta(hours=3))
            for u in reposts:
                await self.put(CommunityRepost, id=sid("prepost", f"{i}:{u['idx']}"), post_id=pid, user_id=u["id"],
                               quote_text=rng.choice([None, "同感", "转给想去的朋友"]), created_at=created + timedelta(hours=5))
            for c in range(ncom):
                cu = rng.choice(users)
                await self.put(CommunityComment, id=sid("pcom", f"{i}:{c}"), post_id=pid, author_id=cu["id"],
                               content=rng.choice(POST_COMMENTS), status="visible", created_at=created + timedelta(hours=1 + c * 4))
        await self.stage(f"plaza: {count} posts ({n_media} images) with likes/comments/bookmarks/reposts")

    # -- 6. clubs & guilds ---------------------------------------------------------------------------------
    async def seed_clubs_guilds(self):
        from sqlalchemy import select

        from app.models import Club, ClubMember, Conversation, ConversationMember, Guild, GuildFollow

        rng = random.Random(f"{self.a.seed}:clubs")
        users = [u for u in self.users if u["status"] == "active"]
        by_idx = {u["idx"]: u for u in self.users}
        for k, (key, name, topic, city, tags, icon, summary) in enumerate(CLUB_SPECS):
            cid = sid("club", key)
            creator = by_idx[1 + (k % 3)] if len(self.users) >= 3 else users[0]
            mem = rng.sample([u for u in users if u["id"] != creator["id"]], min(len(users) - 1, rng.randint(6, 20)))
            await self.put(Club, id=cid, name=name, topic=topic, city=city, summary=summary, tags=tags, system_image=icon,
                           creator_id=creator["id"], is_official=False, status="active", member_count=len(mem) + 1,
                           weekly_active=int((len(mem) + 1) * 0.6), conversation_id=sid("conv", f"club:{key}"), created_at=ago(days=rng.randint(10, 60)))
            await self.db.flush()
            conv = sid("conv", f"club:{key}")
            await self.put(Conversation, id=conv, kind="circle", im_conversation_id=f"noop_group_{creator['id'].hex[:12]}", title=name,
                           owner_id=creator["id"], related_circle_id=cid, last_message_preview=rng.choice(["本周六集合，报名接龙～", "欢迎新朋友！", "[图片]"]),
                           last_message_at=ago(hours=rng.randint(1, 36)), status="active", created_at=ago(days=30), meta={"seed": True})
            for j, u in enumerate([creator] + mem):
                role = "owner" if j == 0 else ("admin" if j == 1 else "member")
                await self.put(ClubMember, id=sid("clubmem", f"{key}:{u['idx']}"), club_id=cid, user_id=u["id"], role=role,
                               status="active", nickname=None, joined_at=ago(days=rng.randint(1, 30)),
                               last_active_at=ago(hours=rng.randint(1, 120)))
                await self.put(ConversationMember, id=sid("cmem", f"{conv}:{u['idx']}"), conversation_id=conv, user_id=u["id"],
                               role=role, unread_count=0 if j == 0 else rng.choice([0, 0, 3]), status="active", joined_at=ago(days=10))
            self.clubs.append(dict(id=cid, key=key, name=name))
        # official clubs: add some members (+ group chat when the official club has none yet)
        offs = list((await self.db.execute(select(Club).where(Club.is_official.is_(True)))).scalars())
        for club in offs:
            ckey = str(club.id)[-3:]
            local = [u for u in users if club.city.startswith(u["city"])] or users
            pick = rng.sample(local, min(len(local), rng.randint(4, 10)))
            conv_id = club.conversation_id
            if conv_id is None:
                conv_id = sid("conv", f"offclub:{ckey}")
                club.conversation_id = conv_id
                await self.put(Conversation, id=conv_id, kind="circle", im_conversation_id=f"noop_group_off{ckey}", title=club.name,
                               owner_id=None, related_circle_id=club.id, last_message_preview="欢迎加入！", last_message_at=ago(hours=9),
                               status="active", created_at=ago(days=30), meta={"seed": True})
                await self.db.flush()
            for u in pick:
                await self.put(ClubMember, id=sid("clubmem", f"off{ckey}:{u['idx']}"), club_id=club.id, user_id=u["id"], role="member",
                               status="active", joined_at=ago(days=rng.randint(1, 30)), last_active_at=ago(hours=rng.randint(1, 120)))
                if str(conv_id).startswith(SEED_PREFIX):
                    await self.put(ConversationMember, id=sid("cmem", f"{conv_id}:{u['idx']}"), conversation_id=conv_id, user_id=u["id"],
                                   role="member", status="active", joined_at=ago(days=5))
        # guilds (ops-curated companion guilds)
        comp_users = [u for u in users if u["idx"] % 5 == 2]
        for k, (key, name, spec, city, tags, icon, price, summary) in enumerate(GUILD_SPECS):
            gid = sid("guild", key)
            owner = comp_users[k % len(comp_users)] if comp_users else users[0]
            await self.put(Guild, id=gid, name=name, specialty=spec, city=city, summary=summary, tags=tags, system_image=icon,
                           price_from_cents=price, owner_user_id=owner["id"], status="active", created_at=ago(days=40))
            await self.db.flush()
            for u in rng.sample(users, min(len(users), rng.randint(5, 15))):
                await self.put(GuildFollow, id=sid("gfollow", f"{key}:{u['idx']}"), guild_id=gid, user_id=u["id"], created_at=ago(days=rng.randint(0, 20)))
            self.clubs.append(dict(id=gid, key=key, name=name, guild=True))
        await self.stage(f"clubs ({len(CLUB_SPECS)} user clubs + members/chats for official clubs) and guilds ({len(GUILD_SPECS)})")

    # -- 7. companions -------------------------------------------------------------------------------------
    async def seed_companions(self):
        from app.models import (CompanionLeaderboard, CompanionProfile, CompanionReview, CompanionService, CompanionSlot)

        rng = random.Random(f"{self.a.seed}:companions")
        cands = [u for u in self.users if u["idx"] % 5 == 2 and u["status"] == "active"]
        if len(cands) < 3:
            cands = [u for u in self.users if u["status"] == "active"][:3]
        types = ["offline", "sport", "voice", "photo"]
        guild_keys = [g[0] for g in GUILD_SPECS]
        for k, u in enumerate(cands):
            st = types[k % 4]
            status = "active"
            if len(cands) >= 5 and k == len(cands) - 1:
                status = "rejected"
            elif len(cands) >= 5 and k == len(cands) - 2:
                status = "paused"
            elif len(cands) >= 5 and k == len(cands) - 3:
                status = "pending"
            base_orders = rng.randint(12, 260) if status == "active" else 0
            c = dict(user=u, type=st, status=status, services=[], slots=[], base_orders=base_orders, k=k)
            self.companions.append(c)
            await self.put(CompanionProfile, user_id=u["id"], service_type=st, specialty=SPECIALTIES[st] + " · " + rng.choice(u["tags"]),
                           guild_id=sid("guild", guild_keys[k % 3]) if k < 3 else None,
                           intro=f"{u['name']}，{rng.choice(['认证陪玩', '兼职陪玩', '全职陪玩'])}。擅长{rng.choice(u['tags'])}，准时靠谱，欢迎预约～",
                           response_time_minutes=rng.choice([5, 10, 15, 30, 60]), order_count=base_orders,
                           rating_avg=Decimal(str(round(rng.uniform(4.4, 5.0), 2))) if status == "active" else Decimal("0"),
                           rating_count=int(base_orders * 0.6), verified=status == "active" and u["photo_verified"], status=status,
                           city=u["city"], reviewed_at=ago(days=10) if status != "pending" else None,
                           reject_reason="资料不完整，请补充服务说明与实名认证" if status == "rejected" else None, created_at=ago(days=rng.randint(20, 60)))
            await self.db.flush()
            for j, (title, unit, price, desc) in enumerate(COMPANION_SERVICES[st]):
                svc = sid("csvc", f"{u['idx']}:{j}")
                await self.put(CompanionService, id=svc, companion_id=u["id"], title=title, pricing_unit=unit,
                               price_cents=int(price * rng.choice([0.9, 1.0, 1.1, 1.2])) // 100 * 100, min_units=1,
                               description=desc, sort_order=j, active=True, created_at=ago(days=30))
                c["services"].append(dict(id=svc, title=title, unit=unit, price=int(price * 1.0)))
            # slots: next 7 days (10:00 / 14:00 / 19:00, 2h) + a few past booked ones
            if status in ("active", "paused"):
                for d in range(0, 8):
                    for hh in (10, 14, 19):
                        s = (NOW + timedelta(days=d)).replace(hour=hh, minute=0, second=0)
                        if s <= NOW:
                            continue
                        slot = sid("cslot", f"{u['idx']}:{d}:{hh}")
                        await self.put(CompanionSlot, id=slot, companion_id=u["id"], start_at=s, end_at=s + timedelta(hours=2),
                                       status="open", created_at=ago(days=1))
                        c["slots"].append(dict(id=slot, start=s))
        await self.db.flush()
        # reviews & leaderboards are created together with bookings (commerce); leaderboard here
        act = sorted([c for c in self.companions if c["status"] == "active"], key=lambda c: -c["base_orders"])
        week = f"{NOW.isocalendar().year}W{NOW.isocalendar().week:02d}"
        for period, key in (("day", NOW.strftime("%Y%m%d")), ("week", week), ("month", NOW.strftime("%Y%m"))):
            for rank, c in enumerate(act, 1):
                await self.put(CompanionLeaderboard, id=sid("lb", f"{period}:{c['user']['idx']}"), period=period, period_key=key,
                               companion_id=c["user"]["id"], score=Decimal(str(round(c["base_orders"] * (1 if period == "month" else 0.3), 2))),
                               rank=rank, computed_at=NOW)
        await self.stage(f"companions ({len(self.companions)}): profiles, services, slots, leaderboards")

    # -- 8. orders / wallet / refunds ----------------------------------------------------------------------
    async def seed_commerce(self):
        from sqlalchemy import select, update

        from app.models import (Credential, CompanionBooking, CompanionReview, CompanionSlot, Membership, MembershipPlan, Order,
                                Payment, Refund, WalletAccount, WalletLedger)

        rng = random.Random(f"{self.a.seed}:commerce")
        users = [u for u in self.users if u["status"] == "active"]
        by_idx = {u["idx"]: u for u in self.users}
        orders: list[dict] = []
        refunds: list[dict] = []
        entries: dict[UUID, list] = defaultdict(list)  # user -> [(t, kind, title, subtitle, delta, order_key, method)]
        methods = ["wallet", "wallet", "wechat", "wechat", "alipay"]

        def clamp(user, t, lo_h=6):
            lo = user["created"] + timedelta(hours=lo_h)
            return min(max(t, lo), NOW - timedelta(minutes=5))

        def order(key, user, kind, subject, title, amount, status, method, created, lo_h=6, **extra):
            created = clamp(user, created, lo_h)
            paid = created + timedelta(minutes=1) if status in ("paid", "refunded", "refunding") else None
            no = f"SP{created:%Y%m%d%H%M%S}{hashlib.md5(key.encode()).hexdigest()[:6].upper()}"
            o = dict(key=key, id=sid("order", key), user=user, kind=kind, subject=subject, title=title, amount=amount, status=status,
                     method=method if status != "created" else None, created=created, paid=paid, no=no, **extra)
            orders.append(o)
            if method == "wallet" and paid:
                k = {"activity": "activity_payment", "companion_booking": "booking_payment", "membership": "membership"}[kind]
                entries[user["id"]].append((paid, k, title, no, -amount, key, "wallet"))
            return o

        def refund(o, status, initiator, reason, **extra):
            refunds.append(dict(order=o, status=status, initiator=initiator, reason=reason, **extra))
            if status == "completed" and o["method"] == "wallet":
                kind = "activity_refund" if o["kind"] == "activity" else "booking_refund"
                entries[o["user"]["id"]].append((extra["completed_at"], kind, "退款：" + o["title"], o["no"], o["amount"], o["key"], "wallet"))

        # (a) activity orders
        paid_orders = []
        for a in self.acts:
            if a["fee_type"] != "online_pay" or a["status"] not in ("published", "cancelled"):
                continue
            for u in a["members"]:
                m = rng.choice(methods)
                if a["status"] == "cancelled":
                    o = order(f"act:{a['key']}:{u['idx']}", u, "activity", a["id"], a["title"], a["fee"], "refunded", m, a["created"] + timedelta(hours=rng.randint(3, 60)),
                              meta={"seed": True, "activity_id": str(a["id"])})
                    refund(o, "completed", "system", "活动取消自动退款", completed_at=ago(days=1), started=ago(days=1, hours=1))
                else:
                    o = order(f"act:{a['key']}:{u['idx']}", u, "activity", a["id"], a["title"], a["fee"], "paid", m, a["created"] + timedelta(hours=rng.randint(3, 100)),
                              meta={"seed": True, "activity_id": str(a["id"])})
                    paid_orders.append(o)
        # refund-queue samples on paid activity orders
        samples = [("submitted", "user", "行程有变，无法参加", None), ("processing", "user", "临时有事", None),
                   ("rejected", "user", "活动开始前 2 小时申请", "超出可退款时间范围"), ("completed", "admin", "客服协商退款", None)]
        for o, (st, ini, reason, rej) in zip(paid_orders[1:], samples):
            if st in ("submitted", "processing"):
                o["status"] = "refunding"
            elif st == "completed":
                o["status"] = "refunded"
            t = NOW - timedelta(hours=rng.randint(2, 40))
            refund(o, st, ini, reason, rejection=rej, completed_at=t + timedelta(hours=1) if st == "completed" else None,
                   started=t + timedelta(minutes=20) if st in ("processing", "completed") else None, created=t)
        # unpaid / expired activity orders
        for k, a in enumerate([x for x in self.acts if x["fee_type"] == "online_pay" and x["state"] == "open"][:2]):
            pool = [u for u in users if u not in a["members"] and u["id"] != a["host"]["id"]]
            if pool:
                u = pool[0]
                o = order(f"act:{a['key']}:unpaid{k}", u, "activity", a["id"], a["title"], a["fee"], "pending_payment" if k == 0 else "closed",
                          "wechat", ago(minutes=8) if k == 0 else ago(hours=5), meta={"seed": True})
                o["expire"] = NOW + timedelta(minutes=22) if k == 0 else NOW - timedelta(hours=4, minutes=30)
                if k == 1:
                    o["closed"] = NOW - timedelta(hours=4, minutes=30)

        # (b) companion bookings
        bookings: list[dict] = []
        booked_slots: set = set()
        states_main = ["completed", "completed", "paid", "awaiting_payment", "pending_confirm", "cancelled", "refunded", "completed"]
        states_other = ["completed", "paid", "awaiting_payment", "cancelled"]
        for c in self.companions:
            if c["status"] != "active" or not c["services"]:
                continue
            states = states_main if c["k"] == 0 else states_other[: 2 + (c["k"] % 3)]
            for j, st in enumerate(states):
                buyer_pool = [u for u in users if u["id"] != c["user"]["id"]]
                buyer = by_idx[1] if (c["k"] == 0 and 1 in by_idx and st in ("paid", "awaiting_payment", "pending_confirm", "refunded", "completed") and j < 5) else rng.choice(buyer_pool)
                svc = rng.choice(c["services"])
                units = rng.choice([1, 1, 2])
                amount = svc["price"] * units
                bid = sid("booking", f"{c['user']['idx']}:{j}")
                future = st in ("paid", "awaiting_payment", "pending_confirm")
                if future and c["slots"]:
                    slot = c["slots"][(j * 3 + c["k"]) % len(c["slots"])]
                    sched = slot["start"]
                    slot_id = slot["id"]
                    booked_slots.add(slot_id)
                else:
                    sched = ago(days=rng.randint(2, 20), hours=rng.randint(0, 8))
                    slot_id = sid("cslot", f"past:{c['user']['idx']}:{j}")
                    bookings_slot = dict(id=slot_id, cid=c["user"]["id"], start=sched)
                    self._past_slots = getattr(self, "_past_slots", []) + [bookings_slot]
                created = min(sched - timedelta(days=1, hours=rng.randint(0, 6)), NOW - timedelta(hours=2))
                o = None
                if st in ("awaiting_payment", "paid", "completed", "refunded", "cancelled"):
                    ost = {"awaiting_payment": "pending_payment", "paid": "paid", "completed": "paid", "refunded": "refunded", "cancelled": "cancelled"}[st]
                    o = order(f"bk:{c['user']['idx']}:{j}", buyer, "companion_booking", bid, f"陪玩 · {svc['title']}", amount, ost,
                              rng.choice(methods), created, meta={"seed": True, "booking_id": str(bid)})
                    if st == "awaiting_payment":
                        o["expire"] = NOW + timedelta(minutes=20)
                    if st == "cancelled":
                        o["closed"] = created + timedelta(minutes=30)
                    if st == "refunded":
                        refund(o, "completed", "user", "预约时间冲突", completed_at=created + timedelta(days=1), started=created + timedelta(hours=26))
                b = dict(id=bid, c=c, buyer=buyer, svc=svc, units=units, amount=amount, status=st, sched=sched, slot=slot_id, order=o, created=created, j=j)
                bookings.append(b)
        # (c) memberships
        plans = {p.code: p for p in (await self.db.execute(select(MembershipPlan))).scalars()}
        mem_users = [by_idx[i] for i in (1, 2, 5, 9, 14, 20) if i in by_idx]
        member_specs = []
        for k, u in enumerate(mem_users):
            code = "quarterly" if k % 3 == 1 else "monthly"
            p = plans.get(code)
            if p is None:
                continue
            expired = k == len(mem_users) - 1 and len(mem_users) > 3
            t = ago(days=70) if expired else ago(days=rng.randint(1, 20))
            o = order(f"vip:{u['idx']}", u, "membership", p.id, p.title, p.price_cents, "paid", rng.choice(methods), t, meta={"seed": True, "plan": code})
            member_specs.append((u, p, o, expired))
        # (d) top-ups: enough balance for every wallet payment + some casual top-ups
        welcome = 50_000
        for u in users:
            spend = sum(-e[4] for e in entries[u["id"]] if e[4] < 0)
            if spend > welcome or rng.random() < 0.35:
                amt = max(0, spend - welcome) // 100 * 100 + rng.choice([2000, 5000, 10000, 20000])
                o = order(f"topup:{u['idx']}", u, "wallet_topup", None, "钱包充值", amt, "paid", rng.choice(["wechat", "alipay"]),
                          u["created"] + timedelta(hours=3), lo_h=2, meta={"seed": True})
                entries[u["id"]].append((o["paid"], "top_up", "钱包充值", o["no"], amt, o["key"], o["method"]))
        if 1 in by_idx:
            order("topup:1:closed", by_idx[1], "wallet_topup", None, "钱包充值", 10000, "closed", "wechat", ago(days=2), meta={"seed": True})
            orders[-1]["closed"] = orders[-1]["created"] + timedelta(minutes=30)
        # ── persist ──
        for o in orders:
            await self.put(Order, id=o["id"], order_no=o["no"], user_id=o["user"]["id"], kind=o["kind"], subject_id=o["subject"],
                           subject_title=o["title"], amount_cents=o["amount"], discount_cents=0, payable_cents=o["amount"],
                           status=o["status"], pay_method=o["method"], paid_at=o["paid"], closed_at=o.get("closed"),
                           expire_at=o.get("expire"), idempotency_key=f"seed-{o['key']}", meta=o.get("meta", {"seed": True}), created_at=o["created"])
        await self.db.flush()
        for o in orders:
            pst = {"paid": "succeeded", "refunded": "succeeded", "refunding": "succeeded", "pending_payment": "pending",
                   "closed": "closed", "cancelled": "closed"}.get(o["status"], "pending")
            await self.put(Payment, id=sid("payment", o["key"]), order_id=o["id"], provider=o["method"] or "wechat",
                           provider_txn_id=f"seed_txn_{o['no']}" if pst == "succeeded" else None, amount_cents=o["amount"], status=pst,
                           client_params={"seed": True}, notified_at=o["paid"], created_at=o["created"])
            if o["status"] in ("paid", "refunding", "refunded") and o["kind"] in ("activity", "companion_booking"):
                await self.put(Credential, id=sid("cred", o["key"]), user_id=o["user"]["id"], style="event_ticket",
                               serial_no=("ACT-" if o["kind"] == "activity" else "BKG-") + hashlib.md5(o["key"].encode()).hexdigest()[:16].upper(),
                               related_kind="order", related_id=o["id"],
                               fields={"primary": [{"key": "event", "label": "活动" if o["kind"] == "activity" else "预约", "value": o["title"]}],
                                       "secondary": [{"key": "order", "label": "订单号", "value": o["no"]}]},
                               barcode_message=o["no"], relevant_at=o["paid"],
                               status="voided" if o["status"] == "refunded" else "valid", created_at=o["paid"])
        for k, r in enumerate(refunds):
            o = r["order"]
            await self.put(Refund, id=sid("refund", o["key"]), order_id=o["id"], user_id=o["user"]["id"], amount_cents=o["amount"],
                           reason=r["reason"], detail="", initiator=r["initiator"], status=r["status"],
                           provider_refund_id=f"seed_rf_{o['no']}" if r["status"] == "completed" else None,
                           admin_note="已核实，同意退款" if r["initiator"] == "admin" else ("不符合退款规则" if r["status"] == "rejected" else None),
                           processing_started_at=r.get("started"), completed_at=r.get("completed_at"),
                           rejection_message=r.get("rejection"), created_at=r.get("created") or (r.get("completed_at") or NOW) - timedelta(hours=1))
        # memberships
        for u, p, o, expired in member_specs:
            start = o["paid"]
            await self.put(Membership, id=sid("membership", u["idx"]), user_id=u["id"], plan_code=p.code,
                           status="expired" if expired else "active", started_at=start, expires_at=start + timedelta(days=p.duration_days),
                           auto_renew=False, source_order_id=o["id"], created_at=start)
            await self.put(Credential, id=sid("cred", f"vip:{u['idx']}"), user_id=u["id"], style="store_card",
                           serial_no="VIP-" + hashlib.md5(f"vip{u['idx']}".encode()).hexdigest()[:16].upper(), related_kind="membership",
                           related_id=sid("membership", u["idx"]), fields={"primary": [{"key": "plan", "label": "会员", "value": p.title}]},
                           barcode_message=o["no"], relevant_at=start, status="expired" if expired else "valid", created_at=start)
        # slots for past bookings, bookings, reviews
        for s in getattr(self, "_past_slots", []):
            await self.put(CompanionSlot, id=s["id"], companion_id=s["cid"], start_at=s["start"], end_at=s["start"] + timedelta(hours=2), status="booked", created_at=s["start"] - timedelta(days=3))
        await self.db.flush()
        for b in bookings:
            o = b["order"]
            st = b["status"]
            await self.put(CompanionBooking, id=b["id"], companion_id=b["c"]["user"]["id"], buyer_id=b["buyer"]["id"], service_id=b["svc"]["id"],
                           slot_id=b["slot"], order_id=o["id"] if o else None, units=b["units"], amount_cents=b["amount"], status=st,
                           scheduled_at=b["sched"], confirmed_at=b["created"] + timedelta(minutes=20) if st != "pending_confirm" else None,
                           paid_at=o["paid"] if o and o["paid"] else None, completed_at=b["sched"] + timedelta(hours=2) if st == "completed" else None,
                           cancelled_at=b["created"] + timedelta(minutes=30) if st == "cancelled" else None,
                           cancel_reason="临时有事" if st == "cancelled" else None, idempotency_key=f"seed-bk-{b['c']['user']['idx']}-{b['j']}",
                           meta={"seed": True}, created_at=b["created"])
            if st == "completed":
                await self.put(CompanionReview, id=sid("review", str(b["id"])), booking_id=b["id"], companion_id=b["c"]["user"]["id"],
                               buyer_id=b["buyer"]["id"], rating=rng.choice([4, 5, 5, 5]), content=rng.choice(REVIEWS),
                               created_at=b["sched"] + timedelta(hours=5))
        if booked_slots:
            await self.db.execute(update(CompanionSlot).where(CompanionSlot.id.in_(booked_slots)).values(status="booked"))
        # wallet ledger + accounts (welcome grant first, then chronological)
        for u in users:
            ent = [(u["created"] + timedelta(minutes=1), "welcome", "新用户礼金", None, welcome, f"welcome:{u['idx']}", None)] + entries.get(u["id"], [])
            ent.sort(key=lambda e: e[0])
            bal = 0
            for n, (t, kind, title, sub, delta, okey, method) in enumerate(ent):
                bal += delta
                oid = sid("order", okey) if not okey.startswith("welcome") else None
                await self.put(WalletLedger, id=sid("ledger", f"{u['idx']}:{n}"), user_id=u["id"], kind=kind, title=title, subtitle=sub,
                               balance_delta_cents=delta, amount_cents=abs(delta), balance_after_cents=bal, related_order_id=oid,
                               method=method, created_at=t)
            await self.put(WalletAccount, user_id=u["id"], balance_cents=bal, frozen_cents=0, version=len(ent), updated_at=NOW)
        await self.stage(f"commerce: {len(orders)} orders, {len(refunds)} refunds, {len(bookings)} bookings, "
                         f"{len(member_specs)} memberships, wallet ledgers")

    # -- 9. ops: reports / notifications / announcements / ... --------------------------------------------
    async def seed_ops(self):
        from app.models import (Announcement, DiscoverShelf, DiscoverShelfItem, Feedback, Notification, PushCampaign, Report)

        rng = random.Random(f"{self.a.seed}:ops")
        users = [u for u in self.users if u["status"] == "active"]
        by_idx = {u["idx"]: u for u in self.users}
        pub_posts = [p for p in self.posts if p["status"] == "published"]
        pub_acts = [a for a in self.acts if a["status"] == "published"]
        user_clubs = [c for c in self.clubs if not c.get("guild")]
        banned = next((u for u in self.users if u["status"] == "banned"), None)
        for k, (kind, reason, detail, status) in enumerate(REPORT_SPECS):
            rep = rng.choice(users)
            tu = None
            target_id, title = None, ""
            if kind == "user":
                tu = banned if (banned and "已封禁" in detail) else rng.choice([u for u in users if u["id"] != rep["id"]])
                target_id, title = str(tu["id"]), tu["name"]
            elif kind == "post" and pub_posts:
                p = rng.choice(pub_posts)
                tu, target_id, title = p["author"], str(p["id"]), p["text"][:30]
            elif kind == "activity" and pub_acts:
                a = rng.choice(pub_acts)
                tu, target_id, title = a["host"], str(a["id"]), a["title"]
            elif kind == "comment" and pub_posts:
                p = rng.choice([x for x in pub_posts if x["ncom"] > 0] or pub_posts)
                tu, target_id, title = p["author"], str(sid("pcom", f"{p['i']}:0")), "（评论）" + rng.choice(POST_COMMENTS)
            elif kind == "club" and user_clubs:
                c = rng.choice(user_clubs)
                target_id, title = str(c["id"]), c["name"]
            else:
                tu = rng.choice(users)
                kind, target_id, title = "user", str(tu["id"]), tu["name"]
            if tu is not None and tu["id"] == rep["id"]:
                rep = next(u for u in users if u["id"] != tu["id"])
            created = ago(hours=rng.randint(1, 24 * 6))
            res = {"resolved": rng.choice(["warn", "limit", "takedown", "ban"]) if status == "resolved" else None, "dismissed": "dismiss"}.get(status)
            if status == "resolved" and banned and "已封禁" in detail:
                res = "ban"
            await self.put(Report, id=sid("report", k), reporter_id=rep["id"], target_user_id=tu["id"] if tu else None, target_kind=kind,
                           target_id=target_id, snapshot={"title": title, "exists": True, "seed": True}, reason=reason, detail=detail,
                           status=status, resolution=res, resolved_at=created + timedelta(hours=8) if status != "pending" else None,
                           admin_note="已处理（演示数据）" if status != "pending" else None, created_at=created)
        # notifications
        n_notif = 0
        for u in users:
            cnt = 14 if u["idx"] == 1 else rng.randint(2, 6)
            for j in range(cnt):
                cat, ttl, body, link = NOTIFY_TEMPLATES[(j + u["idx"]) % len(NOTIFY_TEMPLATES)]
                act = rng.choice(pub_acts) if pub_acts else None
                peer = rng.choice(users)
                fmt = dict(t=act["title"] if act else "活动", id=(act["id"] if act else ""), n=peer["name"])
                t = ago(hours=rng.randint(1, 24 * 10))
                await self.put(Notification, id=sid("notif", f"{u['idx']}:{j}"), user_id=u["id"], category=cat, title=ttl,
                               body=body.format(**fmt), deep_link=link.format(**fmt) if link else None, payload={"seed": True},
                               read_at=t + timedelta(minutes=30) if rng.random() < 0.5 else None, created_at=t)
                n_notif += 1
        # announcements
        for k, (title, body, pinned, status) in enumerate(ANNOUNCEMENTS):
            await self.put(Announcement, id=sid("announce", k), title=title, body=body, pinned=pinned, audience="all",
                           publish_at=ago(days=k + 1) if status != "draft" else None,
                           expire_at=ahead(days=30) if status == "published" else (ago(days=2) if status == "archived" else None),
                           status=status, created_at=ago(days=k + 2))
        # push campaigns
        for k, (title, body, st, sent, opened) in enumerate([("【演示】周末活动推荐", "本周有 12 场新活动，点击查看～", "sent", 1280, 342),
                                                           ("【演示】预约提醒", "你有一个陪玩预约即将开始", "scheduled", 0, 0),
                                                           ("【演示】新功能上线（草稿）", "聊天撤回与编辑已上线", "draft", 0, 0)]):
            await self.put(PushCampaign, id=sid("campaign", k), title=title, body=body, deep_link="spark://activities",
                           audience={"city": "上海", "seed": True}, scheduled_at=ahead(hours=20) if st == "scheduled" else (ago(days=3) if st == "sent" else None),
                           status=st, sent_count=sent, open_count=opened, created_at=ago(days=4))
        # discover shelves
        await self.db.flush()
        if pub_acts:
            for k, (title, sub, layout) in enumerate([("【演示】编辑精选", "运营推荐的本周好局", "hero"), ("【演示】本周热门", "报名人数最多", "rail")]):
                shelf = sid("shelf", k)
                await self.put(DiscoverShelf, id=shelf, title=title, subtitle=sub, layout=layout, rule_type="manual", rule={}, city_scope=[],
                               sort_order=90 + k, enabled=True, created_at=ago(days=3))
                await self.db.flush()
                for j, a in enumerate(sorted(pub_acts, key=lambda a: -len(a["members"]))[k * 4: k * 4 + 5]):
                    await self.put(DiscoverShelfItem, id=sid("shelfitem", f"{k}:{j}"), shelf_id=shelf, subject_kind="activity",
                                   subject_id=a["id"], sort_order=j, pinned=j == 0)
        # feedback
        for k, (cat, content, st, reply) in enumerate(FEEDBACKS):
            u = rng.choice(users)
            await self.put(Feedback, id=sid("feedback", k), user_id=u["id"], category=cat, content=content, contact=None, status=st,
                           admin_reply=reply, replied_at=ago(days=1) if reply else None, created_at=ago(days=k + 1))
        await self.stage(f"ops: {len(REPORT_SPECS)} reports, {n_notif} notifications, announcements, campaigns, shelves, feedback")

    # -- 10. analytics events (so the ops dashboards have data) --------------------------------------------
    async def seed_analytics(self, days: int):
        from sqlalchemy import text

        if days <= 0:
            print("  - analytics skipped (--analytics-days 0)")
            return
        from app.modules.analytics.aggregate import AnalyticsAggregator
        from app.modules.analytics.taxonomy import EVENTS
        from app.modules.metrics.service import MetricsService

        rng = random.Random(f"{self.a.seed}:analytics")
        users = [u for u in self.users if u["status"] == "active"]
        pub_acts = [a for a in self.acts if a["status"] == "published"] or self.acts
        pub_posts = [p for p in self.posts if p["status"] == "published"] or self.posts
        clubs = [c for c in self.clubs if not c.get("guild")]
        guilds = [c for c in self.clubs if c.get("guild")]
        comps = [c for c in self.companions if c["status"] == "active"]
        devices = [(f"seed_dev_{u['idx']:04d}", u) for u in users] + [(f"seed_anon_{i:03d}", None) for i in range(max(10, len(users) // 3))]
        models = ["Pixel 7", "Xiaomi 14", "HUAWEI P60", "OPPO Find X7", "vivo X100", "Redmi Note 13", "Honor 90"]
        screens = {"home": "home", "act": "activities", "actd": "activity_detail", "comp": "companions", "compd": "companion_detail",
                   "club": "clubs", "clubd": "club_detail", "plaza": "plaza", "post": "post_detail", "msg": "messages", "me": "profile",
                   "buddy": "buddies", "login": "login", "pay": "checkout", "search": "search"}
        rows: list[dict] = []
        n_dev_first: dict[str, datetime] = {}

        def session(day_off: int, k: int):
            anon, user = rng.choice(devices)
            sess = f"seed_s_{day_off}_{k}"
            hour = rng.choices(range(24), [1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 8, 9, 8, 6, 6, 6, 7, 8, 10, 11, 11, 8, 4])[0]
            t = (NOW - timedelta(days=day_off)).replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
            if t > NOW:
                t = NOW - timedelta(minutes=rng.randint(5, 90))
            plat = "android" if rng.random() < 0.92 else "ios"
            common = dict(anon_id=anon, session_id=sess, platform=plat, app_version=rng.choices(["1.0.0", "1.0.1", "1.1.0"], [2, 3, 5])[0],
                          build_type="release", os_version=rng.choice(["12", "13", "14", "15"]), device_model=rng.choice(models),
                          network_type=rng.choices(["wifi", "5g", "4g"], [5, 3, 2])[0], channel=rng.choice(["official", "huawei", "xiaomi", "oppo"]),
                          user_id=user["id"] if user else None)
            seq = [0]
            n_dev_first[anon] = min(n_dev_first.get(anon, t), t)
            cursor = [t]

            def ev(name, screen=None, props=None, obj=None, duration=None, otype=None, referrer=None):
                if name not in EVENTS:
                    return
                cursor[0] += timedelta(seconds=rng.randint(1, 25))
                if cursor[0] > NOW:
                    cursor[0] = NOW - timedelta(seconds=rng.randint(1, 30))
                seq[0] += 1
                d = EVENTS[name]
                ot = otype or d.object_type
                rows.append(dict(common, event_id=sid("evt", f"{day_off}:{k}:{seq[0]}"), event_name=name, screen=screen, referrer_screen=referrer,
                                 props=json.dumps(props or {}, ensure_ascii=False), occurred_at=cursor[0],
                                 received_at=cursor[0] + timedelta(seconds=rng.randint(1, 4)), object_type=ot if obj else None,
                                 object_id=str(obj) if obj else None, duration_ms=duration, seq=seq[0]))

            logged = user is not None
            ev("app.launched", screens["home"], {"cold_start": True})
            ev("perf.cold_start", screens["home"], {"duration_ms": rng.randint(500, 2600)}, duration=rng.randint(500, 2600))
            if not logged:
                ev("auth.login_viewed", screens["login"])
                if rng.random() < 0.65:
                    ev("auth.sms_requested", screens["login"])
                    if rng.random() < 0.8:
                        ev("auth.login_succeeded", screens["login"], {"is_new_user": rng.random() < 0.3})
                        logged = True
                    else:
                        ev("auth.login_failed", screens["login"], {"reason": "code_wrong"})
            ev("page.viewed", screens["home"], {"tab": "home"})
            for _ in range(rng.choices([1, 2, 3], [5, 3, 1])[0]):
                feat = rng.choices(["act", "comp", "club", "plaza", "msg", "buddy", "search", "me"], [45, 14, 14, 26, 18, 10, 9, 8])[0]
                if feat == "act":
                    sc = screens["act"]
                    ev("page.viewed", sc, {"tab": "activities"}, referrer=screens["home"])
                    ev("activity.feed_viewed", sc, {"shelf_count": rng.randint(2, 5)})
                    shown = rng.sample(pub_acts, min(len(pub_acts), rng.randint(3, 8)))
                    for pos, a in enumerate(shown):
                        ev("item.exposed", sc, {"list_id": "feed", "position": pos}, a["id"], otype="activity")
                    for pos, a in enumerate(shown):
                        if rng.random() < 0.35:
                            ev("item.clicked", sc, {"list_id": "feed", "position": pos}, a["id"], otype="activity")
                            ev("activity.card_clicked", sc, None, a["id"])
                            ev("activity.detail_viewed", screens["actd"], None, a["id"], referrer=sc)
                            if rng.random() < 0.15:
                                ev("activity.favorited", screens["actd"], None, a["id"])
                            if rng.random() < 0.5:
                                paid = a["fee_type"] == "online_pay"
                                ev("activity.join_clicked", screens["actd"], {"paid": paid}, a["id"])
                                if rng.random() < 0.65:
                                    if paid:
                                        ev("commerce.order_created", screens["pay"], {"kind": "activity", "amount_cents": a["fee"]})
                                        ev("commerce.pay_method_selected", screens["pay"], {"method": rng.choice(["wallet", "wechat", "alipay"])})
                                        if rng.random() < 0.82:
                                            ev("commerce.pay_succeeded", screens["pay"], {"method": "wechat", "amount_cents": a["fee"], "kind": "activity"})
                                            ev("activity.join_succeeded", screens["actd"], {"waitlisted": False}, a["id"])
                                        else:
                                            ev("commerce.pay_failed", screens["pay"], {"method": "wechat", "reason": "user_cancel"})
                                    else:
                                        ev("activity.join_succeeded", screens["actd"], {"waitlisted": a["state"] == "full"}, a["id"])
                                else:
                                    ev("activity.join_failed", screens["actd"], {"reason": rng.choice(["full", "network", "not_logged_in"])}, a["id"])
                elif feat == "comp" and comps:
                    sc = screens["comp"]
                    ev("companion.list_viewed", sc, None, referrer=screens["home"])
                    shown = rng.sample(comps, min(len(comps), 4))
                    for pos, c in enumerate(shown):
                        ev("item.exposed", sc, {"list_id": "companions", "position": pos}, c["user"]["id"], otype="companion")
                    if rng.random() < 0.5:
                        c = rng.choice(shown)
                        ev("companion.detail_viewed", screens["compd"], None, c["user"]["id"])
                        if rng.random() < 0.55:
                            ev("companion.slot_selected", screens["compd"], None, c["user"]["id"])
                            if rng.random() < 0.6:
                                ev("companion.booking_created", screens["compd"], None, c["user"]["id"])
                                if rng.random() < 0.75:
                                    ev("commerce.pay_succeeded", screens["pay"], {"method": "wallet", "amount_cents": 9800, "kind": "companion_booking"})
                elif feat == "club" and clubs:
                    sc = screens["club"]
                    ev("club.feed_viewed", sc, None, referrer=screens["home"])
                    if rng.random() < 0.6:
                        c = rng.choice(clubs)
                        ev("club.detail_viewed", screens["clubd"], None, c["id"])
                        if rng.random() < 0.5:
                            ev("club.join_clicked", screens["clubd"], None, c["id"])
                            if rng.random() < 0.7:
                                ev("club.join_succeeded", screens["clubd"], None, c["id"])
                    if guilds and rng.random() < 0.2:
                        g = rng.choice(guilds)
                        ev("guild.detail_viewed", "guild_detail", None, g["id"])
                        if rng.random() < 0.4:
                            ev("guild.followed", "guild_detail", None, g["id"])
                elif feat == "plaza":
                    sc = screens["plaza"]
                    ev("community.feed_viewed", sc, None, referrer=screens["home"])
                    shown = rng.sample(pub_posts, min(len(pub_posts), rng.randint(3, 7)))
                    for pos, p in enumerate(shown):
                        ev("item.exposed", sc, {"list_id": "plaza", "position": pos}, p["id"], otype="post")
                    for p in shown:
                        if rng.random() < 0.3:
                            ev("community.post_viewed", screens["post"], None, p["id"])
                            if rng.random() < 0.5:
                                ev("community.post_liked", screens["post"], None, p["id"])
                    if rng.random() < 0.06:
                        ev("community.compose_opened", sc)
                        if rng.random() < 0.6:
                            ev("community.post_published", sc, None, rng.choice(pub_posts)["id"])
                elif feat == "msg":
                    sc = screens["msg"]
                    ev("message.inbox_viewed", sc, None, referrer=screens["home"])
                    if rng.random() < 0.7:
                        ev("message.conversation_opened", "conversation", {"kind": rng.choice(["direct", "activity", "circle"])})
                        for _m in range(rng.randint(1, 4)):
                            ev("message.sent", "conversation", {"kind": "text"})
                    if rng.random() < 0.1:
                        ev("message.friend_request_sent", sc)
                elif feat == "buddy":
                    ev("buddy.feed_viewed", screens["buddy"], None, referrer=screens["home"])
                    if rng.random() < 0.4:
                        ev("buddy.detail_viewed", screens["buddy"])
                        if rng.random() < 0.5:
                            ev("buddy.greet_sent", screens["buddy"])
                elif feat == "search":
                    q = rng.choice(["羽毛球", "火锅", "徒步", "剧本杀", "夜骑", "摄影", "咖啡"])
                    ev("search.submitted", screens["search"], {"scope": "activity", "query": q, "query_len": len(q), "result_count": rng.randint(0, 12)})
                    if rng.random() < 0.5:
                        ev("search.result_clicked", screens["search"], {"scope": "activity", "position": rng.randint(0, 5)})
                else:
                    ev("profile.viewed", screens["me"], referrer=screens["home"])
                    if rng.random() < 0.15:
                        ev("commerce.topup_succeeded", "wallet", {"method": "wechat", "amount_cents": rng.choice([2000, 5000, 10000])})
                if rng.random() < 0.5:
                    ev("perf.screen_rendered", screens["act"], {"screen": screens["act"], "duration_ms": rng.randint(80, 900)}, duration=rng.randint(80, 900))
                if rng.random() < 0.3:
                    ev("perf.api_latency", None, {"path": "/api/v1/activities", "status": 200, "duration_ms": rng.randint(40, 900)}, duration=rng.randint(40, 900))
                if rng.random() < 0.04:
                    ev("error.api_failed", None, {"path": "/api/v1/activities", "status": rng.choice([500, 502, 504, 429]), "code": 5000})
            if rng.random() < 0.08:
                ev("push.received", None, {"campaign_id": "seed"})
                if rng.random() < 0.4:
                    ev("push.opened", None, {"campaign_id": "seed", "deep_link_type": "activity"})
            ev("app.backgrounded", None, {"duration_ms": rng.randint(20_000, 600_000)}, duration=rng.randint(20_000, 600_000))

        for d in range(days):
            base = int(len(devices) * rng.uniform(0.35, 0.6))
            for k in range(max(15, base + (days - d))):  # slight upward trend
                session(d, k)
        # monthly partitions for the covered range (past months are not pre-created by the app)
        months = sorted({(r["received_at"].year, r["received_at"].month) for r in rows})
        ok_months = set()
        for y, m in months:
            ny, nm = (y + (m == 12), m % 12 + 1)
            try:
                async with self.db.begin_nested():
                    await self.db.execute(text(
                        f"CREATE TABLE IF NOT EXISTS analytics_events_{y:04d}{m:02d} PARTITION OF analytics_events "
                        f"FOR VALUES FROM ('{y:04d}-{m:02d}-01') TO ('{ny:04d}-{nm:02d}-01')"))
                ok_months.add((y, m))
            except Exception as e:  # overlapping partition with another name etc.
                print(f"  ! cannot create partition {y}-{m:02d}: {str(e)[:90]} → skipping that month's events")
        rows = [r for r in rows if (r["received_at"].year, r["received_at"].month) in ok_months]
        if not rows:
            return
        for i in range(0, len(rows), 1500):
            chunk = rows[i:i + 1500]
            await self.db.execute(text("INSERT INTO analytics_event_dedupe (event_id) VALUES (CAST(:event_id AS uuid)) ON CONFLICT (event_id) DO NOTHING"),
                                  [{"event_id": str(r["event_id"])} for r in chunk])
            res = await self.db.execute(text("SELECT event_id FROM analytics_events WHERE event_id = ANY(CAST(:ids AS uuid[])) AND received_at >= :lo"),
                                        {"ids": [str(r["event_id"]) for r in chunk], "lo": ago(days=days + 2)})
            have = {str(x[0]) for x in res}
            chunk = [r for r in chunk if str(r["event_id"]) not in have]
            if not chunk:
                continue
            await self.db.execute(text(
                """INSERT INTO analytics_events (event_id, event_name, user_id, anon_id, session_id, screen, referrer_screen, props, platform,
                       app_version, build_type, os_version, device_model, network_type, city, ip_hash, occurred_at, received_at, schema_version,
                       sdk_version, channel, experiments, object_type, object_id, duration_ms, seq, client_ts, skew_ms)
                   VALUES (CAST(:event_id AS uuid), :event_name, :user_id, :anon_id, :session_id, :screen, :referrer_screen, CAST(:props AS jsonb),
                       :platform, :app_version, :build_type, :os_version, :device_model, :network_type, NULL, NULL, :occurred_at, :received_at, 2,
                       'seed-1.0', :channel, NULL, :object_type, :object_id, :duration_ms, :seq, :occurred_at, 0)"""), chunk)
            self.created["analytics_events"] += len(chunk)
        for anon, first in n_dev_first.items():
            u = next((u for a2, u in devices if a2 == anon), None)
            await self.db.execute(text(
                """INSERT INTO analytics_devices (anon_id, first_seen_at, last_seen_at, user_id, platform, first_app_version, app_version, channel)
                   VALUES (:a, :f, now(), :u, 'android', '1.0.0', '1.1.0', 'official') ON CONFLICT (anon_id) DO NOTHING"""),
                {"a": anon, "f": first, "u": u["id"] if u else None})
        await self.db.commit()
        agg = AnalyticsAggregator(self.db)
        metrics = MetricsService(self.db)
        shanghai_today = (NOW + timedelta(hours=8)).date()
        for off in range(days, -1, -1):
            day = shanghai_today - timedelta(days=off)
            await agg.rebuild_day(day)
            await metrics.rebuild_day(day)
        await self.db.commit()
        print(f"  ✓ analytics: {self.created['analytics_events']} events over {days} days, daily aggregates + metrics_daily rebuilt")


# ───────────────────────── reset ─────────────────────────
async def reset_seed(db, media_root: Path | None, keep_files: bool = False) -> dict:
    """Remove ONLY rows whose id starts with 5eed5eed- (users cascade to almost everything) and their image files."""
    from sqlalchemy import String, cast, delete, select, text, update

    from app.models import (Announcement, Club, Conversation, DiscoverShelf, Guild, MediaAsset, PushCampaign, User)

    out: dict[str, int] = {}
    like = lambda col: cast(col, String).like(SEED_LIKE)  # noqa: E731
    # 1. files of seeded media (before the rows disappear)
    keys = [r[0] for r in await db.execute(select(MediaAsset.object_key).where(like(MediaAsset.id)))]
    removed_files = 0
    if media_root is not None and not keep_files:
        for k in keys:
            p = media_root / k
            if p.is_file():
                p.unlink()
                removed_files += 1
                try:
                    p.parent.rmdir()  # only if empty
                except OSError:
                    pass
    out["media_files_deleted"] = removed_files
    # 2. analytics rows
    for sql in ("DELETE FROM analytics_events WHERE CAST(event_id AS text) LIKE :p",
                "DELETE FROM analytics_event_dedupe WHERE CAST(event_id AS text) LIKE :p"):
        r = await db.execute(text(sql), {"p": SEED_LIKE})
        out[sql.split()[2]] = r.rowcount
    r = await db.execute(text("DELETE FROM analytics_devices WHERE anon_id LIKE 'seed\\_dev\\_%' OR anon_id LIKE 'seed\\_anon\\_%'"))
    out["analytics_devices"] = r.rowcount
    # 3. detach seeded conversations from official clubs, then delete non-cascading seeded rows
    await db.execute(update(Club).where(like(Club.conversation_id)).values(conversation_id=None))
    for model in (Conversation, Club, Guild, Announcement, PushCampaign, DiscoverShelf):
        r = await db.execute(delete(model).where(like(model.id)))
        out[model.__tablename__] = r.rowcount
    # 4. users (cascades: profiles, media, posts, activities, orders, wallet, reports, notifications, …)
    r = await db.execute(delete(User).where(like(User.id)))
    out["users"] = r.rowcount
    await db.commit()
    if out.get("analytics_events"):
        # derived daily aggregates still contain the seeded events → recompute the affected window from raw events
        from app.modules.analytics.aggregate import AnalyticsAggregator
        from app.modules.metrics.service import MetricsService

        agg, metrics = AnalyticsAggregator(db), MetricsService(db)
        today = (NOW + timedelta(hours=8)).date()
        for off in range(61, -1, -1):
            await agg.rebuild_day(today - timedelta(days=off))
            await metrics.rebuild_day(today - timedelta(days=off))
        await db.commit()
        out["aggregates_rebuilt_days"] = 62
    return out


async def reset_seed_default() -> dict:
    """Convenience for tests: reset using the app's own settings."""
    from app.shared.config import settings
    from app.shared.db import SessionLocal

    async with SessionLocal() as db:
        return await reset_seed(db, Path(settings.media_local_root).resolve())


def refuse_in_production(force: bool) -> None:
    from app.shared.config import settings

    vals = {os.environ.get("ENV", ""), os.environ.get("APP_ENV", ""), settings.app_env or ""}
    if any(v.strip().lower() in {"production", "prod"} for v in vals) and not force:
        print("REFUSING to run: ENV/APP_ENV is production. Demo data would pollute real users. Re-run with --force only if you are sure.",
              file=sys.stderr)
        sys.exit(2)


async def count_seeded(db) -> dict:
    from sqlalchemy import String, cast, func, select

    from app.models import (Activity, Club, CommunityPost, CompanionProfile, Conversation, Guild, MediaAsset, Notification, Order,
                            Refund, Report, User)

    res = {}
    for name, model in (("users", User), ("media_assets", MediaAsset), ("activities", Activity), ("community_posts", CommunityPost),
                        ("clubs", Club), ("guilds", Guild), ("companion_profiles", CompanionProfile), ("orders", Order), ("refunds", Refund),
                        ("reports", Report), ("notifications", Notification), ("conversations", Conversation)):
        res[name] = int((await db.execute(select(func.count()).select_from(model).where(cast(model.id if hasattr(model, "id") else model.user_id, String).like(SEED_LIKE)))).scalar_one())
    return res


async def amain(args) -> int:
    from app.shared.config import settings

    refuse_in_production(args.force)
    from sqlalchemy import select

    from app.shared.db import SessionLocal, engine

    media_root = Path(args.media_root or settings.media_local_root).resolve()
    public_base = (args.public_base or settings.media_public_base or "http://localhost:8000").rstrip("/")
    db_url = str(engine.url.render_as_string(hide_password=True))
    print(f"ENV={settings.app_env}  DB={db_url}\nmedia root: {media_root}  (storage_driver={settings.storage_driver})\nimage URL base: {public_base}/media/…")
    if settings.storage_driver != "local" and not args.no_images:
        print("NOTE: STORAGE_DRIVER is not 'local' — generated files are written to the local media root and are NOT uploaded to OSS. "
              "Upload that directory to the bucket (same keys) or run with --no-images.")
    async with SessionLocal() as db:
        if args.reset or args.reseed:
            print("Resetting seeded data …")
            out = await reset_seed(db, media_root)
            print("  removed:", ", ".join(f"{k}={v}" for k, v in out.items() if v))
            if args.reset and not args.reseed:
                return 0
        images = ImageFactory(media_root, public_base, enabled=not args.no_images, font=args.font)
        print(f"images: {images.mode}")
        if args.users < 8:
            print("--users must be >= 8", file=sys.stderr)
            return 1
        rng = random.Random(args.seed)
        s = Seeder(db, args, images, rng)
        print(f"Seeding (users={args.users}, seed={args.seed}) …")
        await s.bootstrap()
        await s.seed_users(args.users, args.password)
        await s.seed_trust()
        await s.seed_social()
        await s.seed_activities()
        await s.seed_posts()
        await s.seed_clubs_guilds()
        await s.seed_companions()
        await s.seed_commerce()
        await s.seed_ops()
        await s.seed_analytics(args.analytics_days)
        cnt = await count_seeded(db)
    print("\n=== summary ===")
    print("new rows this run :", ", ".join(f"{k}={v}" for k, v in sorted(s.created.items())) or "(nothing — already seeded)")
    print("already present   :", sum(s.skipped.values()), "rows skipped (idempotent re-run)")
    print("seeded rows total :", ", ".join(f"{k}={v}" for k, v in cnt.items()))
    print(f"image files written: {len(images.files)} under {media_root}")
    print(f"\nLogin  : phone {PHONE_BASE + 1} … {PHONE_BASE + args.users} (NN = 01..{args.users:02d}); password '{args.password}' (POST /api/v1/auth/password/login) "
          f"or SMS dev code {settings.sms_dev_code} when SMS_ALLOW_DEV_CODE=true")
    print("  18600000001 林夏 主账号(好友/订单/钱包/通知最多)  18600000002 周屿 陪玩+会员  18600000003 苏晚 活动发起人")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed realistic demo data (idempotent). Everything seeded has id prefix 5eed5eed-.")
    ap.add_argument("--users", type=int, default=60, help="number of demo users (default 60, min 8)")
    ap.add_argument("--seed", default="42", help="random seed for deterministic content (default 42)")
    ap.add_argument("--reset", action="store_true", help="delete ONLY seeded data (and its image files), then exit")
    ap.add_argument("--reseed", action="store_true", help="reset then seed again")
    ap.add_argument("--no-images", action="store_true", help="do not generate image files / media rows (avatars & covers stay empty)")
    ap.add_argument("--force", action="store_true", help="allow running when ENV/APP_ENV=production")
    ap.add_argument("--public-base", default="", help="URL base baked into media URLs (default MEDIA_PUBLIC_BASE or http://localhost:8000)")
    ap.add_argument("--media-root", default="", help="media directory (default MEDIA_LOCAL_ROOT as seen by this process)")
    ap.add_argument("--password", default=DEFAULT_PASSWORD, help=f"password for all demo users (default {DEFAULT_PASSWORD})")
    ap.add_argument("--analytics-days", type=int, default=14, help="days of analytics events to synthesise (0 = skip, default 14, max 60)")
    ap.add_argument("--font", default="", help="path to a CJK .ttf/.ttc font for Chinese text on generated images")
    args = ap.parse_args()
    args.analytics_days = max(0, min(args.analytics_days, 60))
    if len(args.password) < 8:
        ap.error("--password must be at least 8 characters")
    sys.exit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
