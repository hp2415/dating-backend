"""Official seed clubs / guilds (ids match the Android SampleData so deep links keep working)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Club, ClubStatus, Guild, GuildStatus

OFFICIAL_CLUBS = [
    dict(id='C0000000-0000-4000-8000-000000000101', name='黄浦夜骑群', topic='骑行', city='上海 · 黄浦', member_count=286, weekly_active=48, tags=['夜骑', '滨江', '入门友好'], summary='免费兴趣圈。工作日夜骑、周末轻局，分享路线和集合点。', system_image='bicycle'),
    dict(id='C0000000-0000-4000-8000-000000000102', name='徐汇桌游群', topic='娱乐', city='上海 · 徐汇', member_count=412, weekly_active=63, tags=['桌游', '剧本杀', 'KTV'], summary='周末桌游、剧本杀、KTV 自由组局，缺人来群里喊。', system_image='gamecontroller'),
    dict(id='C0000000-0000-4000-8000-000000000103', name='松江徒步群', topic='户外', city='上海 · 松江', member_count=198, weekly_active=31, tags=['爬山', '徒步', '骑行'], summary='周末轻松户外，爬山骑行随缘组队。', system_image='figure.hiking'),
    dict(id='C0000000-0000-4000-8000-000000000104', name='静安羽球群', topic='运动', city='上海 · 静安', member_count=354, weekly_active=72, tags=['羽毛球', '双打', '约场'], summary='水平相近自由开黑，群内互约场地。加入免费，场地费 AA。', system_image='figure.badminton'),
    dict(id='C0000000-0000-4000-8000-000000000105', name='徐汇吃喝群', topic='美食', city='上海 · 徐汇', member_count=521, weekly_active=89, tags=['火锅局', '烧烤', '探店'], summary='交换好吃不贵清单，组火锅烧烤拼桌。', system_image='fork.knife'),
    dict(id='C0000000-0000-4000-8000-000000000106', name='浦东夜跑群', topic='运动', city='上海 · 浦东', member_count=167, weekly_active=40, tags=['夜跑', '骑行'], summary='工作日夜跑夜骑，欢迎下班后来。', system_image='figure.run'),
    dict(id='C0000000-0000-4000-8000-000000000107', name='黄浦探店群', topic='玩乐', city='上海 · 黄浦', member_count=233, weekly_active=27, tags=['逛街', '探店', '夜市'], summary='周末逛街吃吃逛逛，不硬性购物。', system_image='bag'),
    dict(id='C0000000-0000-4000-8000-000000000111', name='锦江夜骑群', topic='骑行', city='成都 · 锦江', member_count=312, weekly_active=55, tags=['夜骑', '东湖', '入门友好'], summary='东湖 / 锦江夜骑，配速友好，欢迎第一次来的同好。', system_image='bicycle'),
    dict(id='C0000000-0000-4000-8000-000000000112', name='武侯火锅群', topic='美食', city='成都 · 武侯', member_count=486, weekly_active=91, tags=['火锅', '串串', '探店'], summary='控辣、控预算拼桌，店单每周更新。', system_image='fork.knife'),
    dict(id='C0000000-0000-4000-8000-000000000113', name='高新羽球群', topic='运动', city='成都 · 高新区', member_count=268, weekly_active=64, tags=['羽毛球', '双打', '约场'], summary='水平相近开黑，群内互约场馆。', system_image='figure.badminton'),
    dict(id='C0000000-0000-4000-8000-000000000114', name='宽窄慢逛群', topic='玩乐', city='成都 · 青羊', member_count=194, weekly_active=33, tags=['漫步', '市集', '咖啡'], summary='宽窄 / 少城慢逛，拍照喝茶不赶场。', system_image='cup.and.saucer'),
    dict(id='C0000000-0000-4000-8000-000000000115', name='龙泉徒步群', topic='户外', city='成都 · 龙泉驿', member_count=221, weekly_active=38, tags=['徒步', '看花', '露营'], summary='周末轻徒步，节奏慢，重点呼吸和拍照。', system_image='figure.hiking'),
]

OFFICIAL_GUILDS = [
    dict(id='C0000000-0000-4000-8000-000000000201', name='夜骑领队工会', specialty='骑行陪玩', city='上海 · 黄浦', price_from_cents=12800, tags=['夜骑', '入门', '领队'], summary='认证夜骑领队，路线规划与配速陪跑，按时计费。', system_image='bicycle'),
    dict(id='C0000000-0000-4000-8000-000000000202', name='探店陪吃社', specialty='线下陪玩', city='上海 · 徐汇', price_from_cents=13800, tags=['探店', '美食', '陪吃'], summary='熟门熟路陪吃陪逛，控预算不劝酒。', system_image='fork.knife'),
    dict(id='C0000000-0000-4000-8000-000000000203', name='剧本杀主持人联盟', specialty='活动陪玩', city='上海 · 静安', price_from_cents=15800, tags=['剧本杀', '主持', '开黑'], summary='资深主持人驻场，可约整场或补位。', system_image='theatermasks'),
    dict(id='C0000000-0000-4000-8000-000000000204', name='夜跑陪跑站', specialty='运动陪玩', city='上海 · 普陀', price_from_cents=11800, tags=['夜跑', '拉伸', '陪跑'], summary='按配速分组陪跑，跑后拉伸指导。', system_image='figure.run'),
    dict(id='C0000000-0000-4000-8000-000000000205', name='展览讲解小分队', specialty='文化陪玩', city='上海 · 黄浦', price_from_cents=14800, tags=['展览', '讲解', '拍照'], summary='策展向讲解 + 出片指导，适合周末展览。', system_image='building.columns'),
    dict(id='C0000000-0000-4000-8000-000000000211', name='锦江夜骑领队会', specialty='骑行陪玩', city='成都 · 锦江', price_from_cents=11800, tags=['夜骑', '东湖', '领队'], summary='认证夜骑领队，东湖 / 锦江配速陪骑。', system_image='bicycle'),
    dict(id='C0000000-0000-4000-8000-000000000212', name='成都火锅陪吃社', specialty='线下陪玩', city='成都 · 武侯', price_from_cents=12800, tags=['火锅', '串串', '陪吃'], summary='熟门熟路陪吃，帮你控辣控预算。', system_image='fork.knife'),
    dict(id='C0000000-0000-4000-8000-000000000213', name='高新羽球陪练站', specialty='运动陪玩', city='成都 · 高新区', price_from_cents=15800, tags=['羽毛球', '陪练', '纠正'], summary='约场陪练与轻度技术纠正，场地费另计。', system_image='figure.badminton'),
    dict(id='C0000000-0000-4000-8000-000000000214', name='少城漫步讲解社', specialty='文化陪玩', city='成都 · 青羊', price_from_cents=13800, tags=['漫步', '历史', '拍照'], summary='宽窄 / 少城路线讲解 + 出片点位。', system_image='building.columns'),

]


async def ensure_official_clubs(db: AsyncSession) -> int:
    """Idempotent: insert missing official clubs/guilds, never overwrite ops edits."""
    from uuid import UUID

    created = 0
    for row in OFFICIAL_CLUBS:
        cid = UUID(row["id"])
        if await db.get(Club, cid) is None:
            db.add(Club(**{**row, "id": cid}, is_official=True, status=ClubStatus.ACTIVE.value))
            created += 1
    for row in OFFICIAL_GUILDS:
        gid = UUID(row["id"])
        if await db.get(Guild, gid) is None:
            db.add(Guild(**{**row, "id": gid}, status=GuildStatus.ACTIVE.value))
            created += 1
    await db.commit()
    return created
